import asyncio
import json
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from redis.exceptions import TimeoutError as RedisTimeoutError

from backend.core.redis_client import (
    STREAM_TASK_EVENTS,
    get_redis,
    ensure_consumer_group,
    STREAM_TASKS,
    STREAM_FINDINGS,
    STREAM_TASK_READY,
    WORKER_GROUP,
    publish_log,
    publish_message,
)
from backend.core.database import async_session
from backend.models.research_task import ResearchTask, TaskStatus
from backend.models.research_finding import ResearchFinding
from backend.agents.research.worker import ResearchWorker  # your existing worker

logger = logging.getLogger(__name__)

class ResearchWorkerConsumer:
    def __init__(self):
        self.worker = ResearchWorker()

    async def run(self, shutdown_event: asyncio.Event, consumer_id: str = "worker-1"):
        rd = await get_redis()
        await ensure_consumer_group(rd, STREAM_TASKS, WORKER_GROUP)
        await self._claim_pending(rd, STREAM_TASKS, WORKER_GROUP, consumer_id)

        logger.info(f"Worker consumer {consumer_id} started. Listening on {STREAM_TASKS}")

        while not shutdown_event or not shutdown_event.is_set():
            try:
                # Read new tasks from stream (pending + new)
                # '>' means read new messages that have not been delivered to this consumer
                messages = await rd.xreadgroup(
                    groupname=WORKER_GROUP,
                    consumername=consumer_id,
                    streams={STREAM_TASKS: ">"},
                    count=1,          # process one task at a time
                    block=1000,       # wait 5 seconds if no message
                )

                if not messages:
                    continue

                # messages is a list: [(stream_name, [(message_id, fields), ...])]
                for stream_name, msg_list in messages:
                    for msg_id, fields in msg_list: # type: ignore
                        logger.info(f"Received task: {msg_id}")
                        task_id_str = fields.get("task_id")
                        query = fields.get("query")

                        if not task_id_str or not query:
                            logger.error(f"Invalid message fields: {fields}")
                            await rd.xack(STREAM_TASKS, WORKER_GROUP, msg_id)
                            continue

                        # Process the task
                        success = await self.process_task(task_id_str, query)

                        if success:
                            await rd.xack(STREAM_TASKS, WORKER_GROUP, msg_id)
                        else:
                            # Could retry or move to DLQ; for now just ack to avoid infinite loop
                            logger.error(f"Task {task_id_str} failed, acknowledging anyway.")
                            await rd.xack(STREAM_TASKS, WORKER_GROUP, msg_id)
            except RedisTimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in consumer loop: {e}", exc_info=True)
                await asyncio.sleep(1)  # avoid tight loop on continuous errors
    
    async def _claim_pending(self, rd, stream, group, consumer_id):
        """Acknowledge all pending messages for this consumer group."""
        try:
            # Fetch pending info
            pending = await rd.xpending(stream, group)
            if pending and pending.get("pending", 0) > 0:
                # Auto-claim and acknowledge everything
                claimed = await rd.xautoclaim(
                    stream, group, consumer_id, min_idle_time=0, start="0-0"
                )
                for msg_id, fields in claimed[1]:
                    await rd.xack(stream, group, msg_id)
        except Exception as e:
            logger.warning(f"Could not auto-ack pending messages: {e}")
            
    async def process_task(self, task_id_str: str, query: str) -> bool:
        """Execute a single task: search, crawl, store findings, publish finding IDs."""
        from uuid import UUID
        try:
            task_uuid = UUID(task_id_str)
        except ValueError:
            logger.error(f"Invalid task UUID: {task_id_str}")
            return False

        async with async_session() as session:
            # Fetch task from DB
            task: Optional[ResearchTask] = await session.get(ResearchTask, task_uuid)
            if not task:
                logger.error(f"Task {task_uuid} not found in DB")
                return False

            # Mark as running
            task.status = TaskStatus.RUNNING
            await session.commit()

            try:
                # Delegate to ResearchWorker: search + crawl
                # research() returns list[dict] with 'url', 'markdown'
                findings_data: list[dict] = await self.worker.research(query)

                if not findings_data:
                    logger.warning(f"No findings for task {task_uuid}")
                    task.status = TaskStatus.COMPLETED
                    await session.commit()
                    return True

                md = ""
                # Create ResearchFinding records and collect IDs
                finding_ids = []
                for item in findings_data:
                    finding = ResearchFinding(
                        task_id=task_uuid,
                        job_id = task.job_id,
                        query=query,
                        url=item["url"],
                        markdown_content=item["markdown"],
                        title="",               # you can extract if available
                        snippet="",             # you can pass snippet through worker
                    )
                    print(f"Adding finding for URL: {item['url']} with markdown length {len(item['markdown'].split())} words")
                    md += item["markdown"] + "\n\n\n\n"
                    session.add(finding)
                    await session.flush()  # get the generated ID
                    finding_ids.append(str(finding.id))

                print(f"markdown length {len(md.split())} words")
                # Publish each finding ID to the findings stream
                rd = await get_redis()
                for fid in finding_ids:
                    await publish_message(rd, STREAM_FINDINGS, {"finding_id": fid})

                # Mark task as completed
                task.status = TaskStatus.COMPLETED
                await session.commit()
                rd = await get_redis()
                await publish_message(rd, STREAM_TASK_READY, {"task_id": task_id_str})
                await publish_log(rd, str(finding.job_id), "research", f"Task {task_id_str} completed with {len(findings_data)} findings saved.")
                logger.info(f"Task {task_id_str} completed, {len(findings_data)} findings saved.")
                
                await publish_message(rd, STREAM_TASK_EVENTS, {
                    "task_id": task_id_str,
                    "event": "research_completed"
                })
                
                return True

            
  
            except Exception as e:
                logger.error(f"Task {task_uuid} failed: {e}", exc_info=True)
                task.status = TaskStatus.FAILED
                await session.commit()
                return False