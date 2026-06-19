import asyncio, json, logging
from uuid import UUID
from sqlalchemy import select
from redis.asyncio import Redis
from backend.core.redis_client import (
    get_redis, ensure_consumer_group, STREAM_TASK_READY, STREAM_CLAIMS,
    CLAIM_GROUP, publish_message
)
from backend.core.database import async_session
from backend.core.llm import llm
from backend.models.research_task import ResearchTask
from backend.models.research_finding import ResearchFinding
from backend.models.claim_db import Claim
from backend.agents.claim.agent import ClaimExtraction  # your class

logger = logging.getLogger(__name__)

class ClaimExtractorConsumer:
    def __init__(self):
        self.extractor = ClaimExtraction()   # uses your improved prompt and Titanium parsing

    async def run(self, consumer_id: str = "claim-extractor-1"):
        rd = await get_redis()
        await ensure_consumer_group(rd, STREAM_TASK_READY, CLAIM_GROUP)
        logger.info("ClaimExtractor started, listening on task_ready stream.")
        while True:
            try:
                messages = await rd.xreadgroup(
                    groupname=CLAIM_GROUP, consumername=consumer_id,
                    streams={STREAM_TASK_READY: ">"}, count=1, block=5000
                )
                if not messages:
                    continue
                for stream_name, msg_list in messages:
                    for msg_id, fields in msg_list: # type: ignore
                        task_id = fields.get("task_id")
                        if not task_id:
                            await rd.xack(STREAM_TASK_READY, CLAIM_GROUP, msg_id)
                            continue
                        await self.process_task(task_id)
                        await rd.xack(STREAM_TASK_READY, CLAIM_GROUP, msg_id)
            except Exception as e:
                logger.error(f"Consumer loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def process_task(self, task_id_str: str):
        async with async_session() as session:
            task = await session.get(ResearchTask, UUID(task_id_str))
            if not task:
                return

            # Fetch all findings for this task
            stmt = select(ResearchFinding).where(ResearchFinding.task_id == task.id)
            findings = (await session.execute(stmt)).scalars().all()

            if not findings:
                logger.warning(f"No findings for task {task_id_str}")
                return

            # Combine markdowns into one giant string, adding separators and URL context
            combined_md = ""
            for f in findings:
                if f.markdown_content:
                    combined_md += f"{f.markdown_content}\n\n---\n\n"

            # Optionally prepend the original query for context
            query_context = task.query
            full_text = f"Research question: {query_context}\n\n{combined_md}"

            # Use your chunking-capable extractor
            claims = await self.extractor.extract_claims_from_finding_parallel(text=combined_md, query=query_context)
            # Alternative: add a method to ClaimExtractor that accepts raw text + query

            if not claims:
                logger.info(f"No claims extracted for task {task_id_str}")
                return

            # Save claims to DB
            claim_ids = []
            for c in claims:
                claim = Claim(
                    finding_id=findings[0].id,  # or a special “task” claim; for simplicity use first finding
                    text=c.claim,
                    evidence=c.evidence,
                    source_url="",  # aggregated, so no single URL
                    confidence=c.confidence,
                )
                session.add(claim)
                await session.flush()
                claim_ids.append(str(claim.id))
            await session.commit()

            # Publish claim IDs to research.claims stream
            rd = await get_redis()
            for cid in claim_ids:
                await publish_message(rd, STREAM_CLAIMS, {"claim_id": cid})
            logger.info(f"Task {task_id_str}: {len(claims)} claims extracted.")