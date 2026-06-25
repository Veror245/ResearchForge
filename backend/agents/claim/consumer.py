import asyncio, json, logging
import time
from uuid import UUID
from sqlalchemy import select
from redis.asyncio import Redis
from backend.core.redis_client import (
    STREAM_TASK_EVENTS, get_redis, ensure_consumer_group, STREAM_TASK_READY, STREAM_CLAIMS, STREAM_JOBS,
    CLAIM_GROUP, publish_message
)
from redis.exceptions import TimeoutError as RedisTimeoutError
from backend.core.database import async_session
from backend.core.llm import llm
from backend.models.research_job import ResearchJob
from backend.models.research_task import ResearchTask
from backend.models.research_finding import ResearchFinding
from backend.models.claim_db import Claim
from backend.agents.claim.agent import ClaimExtraction  # your class

logger = logging.getLogger(__name__)

STREAM = STREAM_TASK_EVENTS

class ClaimExtractorConsumer:
    def __init__(self):
        self.extractor = ClaimExtraction()   # uses your improved prompt and Titanium parsing

    async def run(self, consumer_id: str = "claim-extractor-1"):
        rd = await get_redis()
        await ensure_consumer_group(rd, STREAM, CLAIM_GROUP)
        logger.info("ClaimExtractor started, listening on task_ready stream.")
        while True:
            try:
                messages = await rd.xreadgroup(
                    groupname=CLAIM_GROUP, consumername=consumer_id,
                    streams={STREAM: ">"}, count=1, block=5000
                )
                if not messages:
                    continue
                for stream_name, msg_list in messages:
                    for msg_id, fields in msg_list: # type: ignore
                        if fields.get("event") != "job_researched":
                            await rd.xack(STREAM, CLAIM_GROUP, msg_id)
                            continue
                        job_id = fields.get("job_id")
                        if not job_id:
                            await rd.xack(STREAM, CLAIM_GROUP, msg_id)
                            continue
                        await self.process_task(job_id)
                        await rd.xack(STREAM, CLAIM_GROUP, msg_id)
            
            except RedisTimeoutError:
                continue
            except Exception as e:
                logger.error(f"Consumer loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def process_task(self, job_id_str: str):
        async with async_session() as session:
            job = await session.get(ResearchJob, UUID(job_id_str))
            if not job:
                return

            # Fetch all findings for this job
            stmt = select(ResearchFinding).where(ResearchFinding.job_id == job.id)
            findings = (await session.execute(stmt)).scalars().all()

            if not findings:
                logger.warning(f"No findings for job {job_id_str}")
                return
            print(f"job {job_id_str} has {len(findings)} findings. Extracting claims...")
            # Combine markdowns into one giant string, adding separators and URL context
            combined_md = ""
            for f in findings:
                if f.markdown_content:
                    combined_md += f"{f.markdown_content}\n\n---\n\n"

            # Optionally prepend the original query for context
            query_context = job.query
            full_text = f"Research question: {query_context}\n\n{combined_md}"

            print(f"length of full text for claim extraction: {len(combined_md.split())} words")
            # Use your chunking-capable extractor
            t0 = time.time()
            all_claims = await self.extractor.extract_claims_from_finding_parallel(text=combined_md, query=query_context)
            t1 = time.time()
            print(f"Time taken for claim extraction: {t1 - t0:.2f} seconds")
            # Alternative: add a method to ClaimExtractor that accepts raw text + query

            t0 = time.time()
            claims = await self.extractor.dedupe_claims(all_claims)
            t1 = time.time()
            print(f"Time taken for claim deduplication: {t1 - t0:.2f} seconds")
            print(f"job {job_id_str}: Extracted {len(claims)} unique claims from {len(all_claims)} total claims.")

            if not claims:
                logger.info(f"No claims extracted for job {job_id_str}")
                return

            job_uuid = UUID(job_id_str)
            # Save claims to DB
            claim_ids = []
            for c in claims:
                claim = Claim(
                    job_id=job_uuid,
                    finding_id=None,  # or a special “job” claim; for simplicity use first finding
                    text=c.claim,
                    evidence=c.evidence,  # aggregated, so no single URL
                    confidence=c.confidence,
                    importance=c.importance,          # add this
                    type=c.type.value,
                    chunk=c.chunk  # store the chunk text if available 
                )
                session.add(claim)
                await session.flush()
                claim_ids.append(str(claim.id))
            await session.commit()

            # Publish claim IDs to research.claims stream
            rd = await get_redis()
            # for cid in claim_ids:
            #     await publish_message(rd, STREAM_CLAIMS, {"claim_id": cid})
            
            await publish_message(rd,   STREAM, {
                "job_id": job_id_str,
                "event": "claims_completed"
            })
            
            logger.info(f"job {job_id_str}: {len(claims)} claims extracted.")