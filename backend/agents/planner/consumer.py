import asyncio, logging
from uuid import uuid4, UUID
from sqlalchemy import select
from redis.asyncio import Redis
from backend.core.redis_client import (
    get_redis, ensure_consumer_group, STREAM_JOBS, STREAM_TASKS,
    STREAM_TASK_EVENTS, JOB_GROUP, PLANNER_GROUP, publish_message
)
from backend.core.database import async_session
from backend.models.research_job import ResearchJob, JobStatus
from backend.models.research_task import ResearchTask, TaskStatus
from backend.models.research_finding import ResearchFinding
from backend.agents.planner.agent import Planner

from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)


class PlannerConsumer:
    def __init__(self):
        self.agent = Planner()

    async def run(self, consumer_id: str = "planner-1"):
        rd = await get_redis()
        await ensure_consumer_group(rd, STREAM_JOBS, JOB_GROUP)
        logger.info("Planner started. Listening on research.jobs")

        while True:
            try:
                messages = await rd.xreadgroup(
                    groupname=JOB_GROUP, consumername=consumer_id,
                    streams={STREAM_JOBS: ">"}, count=1, block=5000
                )
                if not messages:
                    continue
                for _, msg_list in messages:
                    for msg_id, fields in msg_list: # type: ignore
                        query = fields.get("query")
                        if not query:
                            await rd.xack(STREAM_JOBS, JOB_GROUP, msg_id)
                            continue
                        job_id_str = fields.get("job_id")
                        try:
                            job_id = UUID(job_id_str) if job_id_str else uuid4()
                        except ValueError:
                            job_id = uuid4()
                        async with async_session() as session:
                            job = ResearchJob(id=job_id, query=query, status=JobStatus.PENDING)
                            session.add(job)
                            await session.commit()
                        # Launch background task (don't await it)
                        asyncio.create_task(self.process_job(job_id))
                        await rd.xack(STREAM_JOBS, JOB_GROUP, msg_id)
            except RedisTimeoutError:
                continue
            except Exception as e:
                logger.error(f"Planner loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def process_job(self, job_id: UUID):
        """Plan tasks, spawn them, wait for completion, aggregate and publish."""
        try:
            # 1. Get job and plan sub-queries
            async with async_session() as session:
                job = await session.get(ResearchJob, job_id)
                if not job:
                    logger.error(f"Job {job_id} not found")
                    return
                planner_output = await self.agent.plan(job)
                sub_queries = planner_output.sub_queries
                if not sub_queries:
                    logger.error(f"No sub-queries generated for job {job_id}")
                    return

                # 2. Create tasks and publish them
                task_ids = []
                for sub_query in sub_queries:
                    task = ResearchTask(id=uuid4(), query=sub_query, job_id=job_id, status=TaskStatus.PENDING)
                    session.add(task)
                    await session.flush()
                    task_ids.append(task.id)
                    await publish_message(await get_redis(), STREAM_TASKS, {
                        "task_id": str(task.id),
                        "query": sub_query
                    })
                await session.commit()

            # 3. Wait until all tasks are completed (poll DB)
            await self._wait_for_tasks(job_id, task_ids, timeout=600)

            # 4. Aggregate markdown from all findings of these tasks
            combined_md = ""
            async with async_session() as session:
                for tid in task_ids:
                    stmt = select(ResearchFinding).where(ResearchFinding.task_id == tid)
                    findings = (await session.execute(stmt)).scalars().all()
                    for f in findings:
                        if f.markdown_content:
                            combined_md += f"{f.markdown_content}\n\n---\n\n"
                # Update job status
                job = await session.get(ResearchJob, job_id)
                if job:
                    job.status = JobStatus.PENDING
                    await session.commit()
            
            logger.info(f"md lenghth {len(combined_md.split())} words for job {job_id}")

            # 5. Publish job_researched event (carrying the combined markdown, or at least job_id)
            rd = await get_redis()
            # Optionally store combined_md in a new column on ResearchJob, or send it directly.
            # For now, we just publish the job_id; the claim extractor will fetch findings by job_id.
            await publish_message(rd, STREAM_TASK_EVENTS, {
                "job_id": str(job_id),
                "event": "job_researched"
            })
            logger.info(f"Job {job_id}: research completed, event published.")
        except Exception as e:
            logger.error(f"Job {job_id} processing failed: {e}", exc_info=True)

    async def _wait_for_tasks(self, job_id: UUID, task_ids: list[UUID], timeout: float = 600):
        """Poll DB until all tasks are done."""
        elapsed = 0
        while elapsed < timeout:
            async with async_session() as session:
                tasks = []
                for tid in task_ids:
                    t = await session.get(ResearchTask, tid)
                    tasks.append(t)
                if all(t and t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) for t in tasks):
                    return
            await asyncio.sleep(2)
            elapsed += 2
        logger.warning(f"Timeout waiting for tasks of job {job_id}")