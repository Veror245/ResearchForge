import asyncio, json, logging
from uuid import UUID
from sqlalchemy import select
from redis.asyncio import Redis
from backend.core.redis_client import (
    get_redis, ensure_consumer_group, STREAM_TASK_READY, STREAM_REPORTS,
    REPORT_GROUP, publish_message
)
from backend.core.database import async_session
from backend.models.research_task import ResearchTask
from backend.models.research_finding import ResearchFinding
from backend.models.claim_db import Claim
from backend.models.report import ResearchReport
from backend.agents.report.agent import ReportGenerator, ReportSchema

from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)

REPORT_GROUP = "report_writers"
STREAM_REPORTS = "research.reports"

class ReportWriterConsumer:
    def __init__(self):
        self.writer = ReportGenerator()

    async def run(self, consumer_id: str = "report-writer-1"):
        rd = await get_redis()
        await ensure_consumer_group(rd, STREAM_TASK_READY, REPORT_GROUP)
        logger.info("Report Writer started. Waiting for task_ready messages.")

        while True:
            try:
                messages = await rd.xreadgroup(
                    groupname=REPORT_GROUP, consumername=consumer_id,
                    streams={STREAM_TASK_READY: ">"}, count=1, block=5000
                )
                if not messages:
                    continue
                for stream_name, msg_list in messages:
                    for msg_id, fields in msg_list: # type: ignore
                        task_id = fields.get("task_id")
                        if not task_id:
                            await rd.xack(STREAM_TASK_READY, REPORT_GROUP, msg_id)
                            continue
                        success = await self.process_report_for_task(task_id)
                        if success:
                            await rd.xack(STREAM_TASK_READY, REPORT_GROUP, msg_id)
                        else:
                            logger.error(f"Report for task {task_id} could not be generated, skipping.")
                            await rd.xack(STREAM_TASK_READY, REPORT_GROUP, msg_id)
            except RedisTimeoutError:
                continue                
            except Exception as e:
                logger.error(f"Consumer loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def wait_for_claims(self, task_id: UUID, timeout: int = 60) -> list[Claim]:
        """Poll until claims appear for the task."""
        elapsed = 0
        while elapsed < timeout:
            async with async_session() as session:
                stmt = select(Claim).where(Claim.task_id == task_id)
                result = await session.execute(stmt)
                claims = result.scalars().all()
                if claims:
                    return claims # type: ignore
            await asyncio.sleep(1)
            elapsed += 1
        return []

    async def process_report_for_task(self, task_id_str: str) -> bool:
        try:
            task_uuid = UUID(task_id_str)
        except ValueError:
            logger.error(f"Invalid task UUID: {task_id_str}")
            return False

        async with async_session() as session:
            task = await session.get(ResearchTask, task_uuid)
            if not task:
                logger.error(f"Task {task_id_str} not found")
                return False

            # Fetch all findings
            stmt = select(ResearchFinding).where(ResearchFinding.task_id == task_uuid)
            findings = (await session.execute(stmt)).scalars().all()
            if not findings:
                logger.warning(f"No findings for task {task_id_str}")
                return False

            # Wait for claims to be ready
            claims = await self.wait_for_claims(task_uuid, timeout=300)
            if not claims:
                logger.warning(f"No claims found for task {task_id_str} after waiting")
                # You might still generate a report without claims, or skip
                # For now, we'll proceed with empty claims (you can change)
            
            md = ""
            for c in claims:
                md += f"- {c.text}\n"
                md += f" {c.evidence}\n\n"
            # Generate report using your ReportWriter
            try:
                report = await self.writer.generate_report(
                    findings=md,
                    query=task.query
                )
                report_data = report.model_dump(exclude_unset=True, exclude_none=True)
            except Exception as e:
                logger.error(f"Report generation failed: {e}", exc_info=True)
                return False

            # Save to database
            report = ResearchReport(
                task_id=task_uuid,
                executive_summary=report_data.get("executive_summary", ""),
                key_findings=report_data.get("key_findings", ""),
                methodology=report_data.get("methodology", ""),
                supporting_evidence=report_data.get("supporting_evidence", ""),
                counterarguments=report_data.get("counterarguments", ""),
                final_assessment=report_data.get("final_assessment", ""),
                confidence_score=report_data.get("confidence_score", 0.0),
            )
            session.add(report)
            await session.commit()

            # Publish to reports stream
            rd = await get_redis()
            await publish_message(rd, STREAM_REPORTS, {"report_id": str(report.id)})
            logger.info(f"Report generated for task {task_id_str}")
            return True