import asyncio, json, logging
from uuid import UUID
from sqlalchemy import select
from redis.asyncio import Redis
from backend.core.redis_client import (
    STREAM_TASK_EVENTS, get_redis, ensure_consumer_group, STREAM_TASK_READY, STREAM_REPORTS,
    REPORT_GROUP, publish_log, publish_message
)
from backend.core.database import async_session
from backend.models.research_job import JobStatus, ResearchJob
from backend.models.research_task import ResearchTask
from backend.models.research_finding import ResearchFinding
from backend.models.claim_db import Claim
from backend.models.report import ResearchReport
from backend.agents.report.agent import ReportGenerator, ReportSchema
from backend.models.debate import Skeptic, Optimist
import numpy as np

from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)

# REPORT_GROUP = "report_writers"
# STREAM_REPORTS = "research.reports"

class ReportWriterConsumer:
    def __init__(self):
        self.writer = ReportGenerator()

    async def run(self, consumer_id: str = "report-writer-1"):
        rd = await get_redis()
        await ensure_consumer_group(rd, STREAM_TASK_EVENTS, REPORT_GROUP)
        logger.info("Report Writer started. Waiting for task_ready messages.")

        while True:
            try:
                messages = await rd.xreadgroup(
                    groupname=REPORT_GROUP, consumername=consumer_id,
                    streams={STREAM_TASK_EVENTS: ">"}, count=1, block=5000
                )
                if not messages:
                    continue
                for stream_name, msg_list in messages:
                    for msg_id, fields in msg_list: # type: ignore
                        if fields.get("event") != "debate_completed":
                            await rd.xack(STREAM_TASK_EVENTS, REPORT_GROUP, msg_id)
                            continue
                        job_id = fields.get("job_id")
                        if not job_id:
                            await rd.xack(STREAM_TASK_EVENTS, REPORT_GROUP, msg_id)
                            continue
                        success = await self.process_report_for_job(job_id)
                        if success:
                            await rd.xack(STREAM_TASK_EVENTS, REPORT_GROUP, msg_id)
                        else:
                            logger.error(f"Report for job {job_id} could not be generated, skipping.")
                            await rd.xack(STREAM_TASK_EVENTS, REPORT_GROUP, msg_id)
            except RedisTimeoutError:
                continue                
            except Exception as e:
                logger.error(f"Consumer loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def wait_for_claims(self, job_id: UUID, timeout: int = 60) -> list[Claim]:
        """Poll until claims appear for the task."""
        elapsed = 0
        while elapsed < timeout:
            async with async_session() as session:
                stmt = select(Claim).where(Claim.job_id == job_id)
                result = await session.execute(stmt)
                claims = result.scalars().all()
                if claims:
                    return claims # type: ignore
            await asyncio.sleep(1)
            elapsed += 1
        return []

    async def process_report_for_job(self, job_id_str: str) -> bool:
        try:
            job_uuid = UUID(job_id_str)
        except ValueError:
            logger.error(f"Invalid job UUID: {job_id_str}")
            return False

        
        async with async_session() as session:
            job = await session.get(ResearchJob, job_uuid)
            if not job:
                logger.error(f"job {job_id_str} not found")
                return False

            # Fetch all findings
            stmt = select(ResearchFinding).where(ResearchFinding.job_id == job_uuid)
            findings = (await session.execute(stmt)).scalars().all()
            if not findings:
                logger.warning(f"No findings for job {job_id_str}")
                return False

            # Wait for claims to be ready
            claims = await self.wait_for_claims(job_uuid, timeout=5)
            if not claims:
                logger.warning(f"No claims found for job {job_id_str} after waiting")
                # You might still generate a report without claims, or skip
                # For now, we'll proceed with empty claims (you can change)
            logger.info(f"Generating report for job {job_id_str}")
            rd = await get_redis()
            await publish_log(rd, job_id_str, "report", 
            f"Generating report for job {job_id_str} with {len(findings)} findings and {len(claims)} claims.")
            
            skeptic_stmt = select(Skeptic).where(Skeptic.job_id == job_uuid)
            skeptics = (await session.execute(skeptic_stmt)).scalars().all()
            if not skeptics:
                logger.warning(f"No skeptic arguments found for job {job_id_str}")
            optimist_stmt = select(Optimist).where(Optimist.job_id == job_uuid)
            optimists = (await session.execute(optimist_stmt)).scalars().all()
            if not optimists:
                logger.warning(f"No optimist arguments found for job {job_id_str}")
            
            md = ""
            cf = []
            for c in claims:
                md += f"- {c.text}\n"
                md += f" {c.evidence}\n\n"
                cf.append(c.confidence)
            confidence = np.mean(cf) if cf else 0.0
            
            md += "\n### Skeptic Arguments\n"
            for s in skeptics:
                md += f"- {s.arguments}\n"
            md += "\n### Optimist Arguments\n"
            for o in optimists:
                md += f"- {o.arguments}\n"
            
            print(len(md.split()), "words in claims markdown")
            # Generate report using your ReportWriter
            try:
                report = await self.writer.generate_report(
                    findings=md,
                    query=job.query
                )
                report_data = report.model_dump(exclude_unset=True, exclude_none=True)
            except Exception as e:
                logger.error(f"Report generation failed: {e}", exc_info=True)
                return False

            # Save to database
            report = ResearchReport(
                job_id=job_uuid,
                executive_summary=report_data.get("executive_summary", ""),
                key_findings=report_data.get("key_findings", ""),
                methodology=report_data.get("methodology", ""),
                supporting_evidence=report_data.get("supporting_evidence", ""),
                counterarguments=report_data.get("counterarguments", ""),
                final_assessment=report_data.get("final_assessment", ""),
                confidence_score=confidence,
            )
            session.add(report)
             
            stmt = select(ResearchJob).where(ResearchJob.id == job_uuid)
            saved_job = (await session.execute(stmt)).scalars().first()
            if saved_job:
                saved_job.status = JobStatus.COMPLETED
            
            await session.commit()

            # Publish to reports stream
            await publish_message(rd, STREAM_TASK_EVENTS, {
                "job_id": job_id_str,
                "event": "report_completed"
            })
            logger.info(f"Report generated for job {job_id_str}")
            return True