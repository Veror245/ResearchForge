import asyncio, logging
from uuid import UUID
from sqlalchemy import select
from redis.asyncio import Redis
from redis.exceptions import TimeoutError as RedisTimeoutError
from backend.core.redis_client import (
    get_redis, ensure_consumer_group, STREAM_TASK_EVENTS, DEBATE_GROUP, publish_message
)
from backend.core.database import async_session
from backend.models.research_job import ResearchJob
from backend.models.claim_db import Claim
from backend.models.critic import Critique
from backend.models.debate import Skeptic, Optimist
from backend.agents.debate.agent import DebateAgent

logger = logging.getLogger(__name__)

class DebateConsumer:
    def __init__(self):
        self.agent = DebateAgent()

    async def run(self, consumer_id: str = "debate-1"):
        rd = await get_redis()
        await ensure_consumer_group(rd, STREAM_TASK_EVENTS, DEBATE_GROUP)
        logger.info("Debate agent started. Waiting for job_critiques_completed...")
        while True:
            try:
                messages = await rd.xreadgroup(
                    groupname=DEBATE_GROUP, consumername=consumer_id,
                    streams={STREAM_TASK_EVENTS: ">"}, count=1, block=5000
                )
                if not messages:
                    continue
                for _, msg_list in messages:
                    for msg_id, fields in msg_list: # type: ignore
                        if fields.get("event") != "critiques_completed":
                            await rd.xack(STREAM_TASK_EVENTS, DEBATE_GROUP, msg_id)
                            continue
                        job_id = fields.get("job_id")
                        if not job_id:
                            await rd.xack(STREAM_TASK_EVENTS, DEBATE_GROUP, msg_id)
                            continue
                        success = await self.process_job(job_id)
                        if success:
                            await rd.xack(STREAM_TASK_EVENTS, DEBATE_GROUP, msg_id)
                        else:
                            logger.error(f"Debate failed for job {job_id}, acking anyway.")
                            await rd.xack(STREAM_TASK_EVENTS, DEBATE_GROUP, msg_id)
            except RedisTimeoutError:
                continue
            except Exception as e:
                logger.error(f"Debate consumer loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def process_job(self, job_id_str: str) -> bool:
        try:
            job_uuid = UUID(job_id_str)
        except ValueError:
            return False

        async with async_session() as session:
            job = await session.get(ResearchJob, job_uuid)
            if not job:
                return False

            # Fetch all claims and critiques for this job
            claims = (await session.execute(
                select(Claim).where(Claim.job_id == job_uuid)
            )).scalars().all()
            critiques = (await session.execute(
                select(Critique).where(Critique.job_id == job_uuid)
            )).scalars().all()

            # Generate debate
            debate_output = await self.agent.generate_debate(job.query, claims, critiques) # type: ignore

            # Save skeptical arguments
            for item in debate_output.skeptic_arguments:
                arg = Skeptic(job_id=job_uuid, arguments=item.arguments)
                session.add(arg)
            # Save optimistic arguments
            for item in debate_output.optimist_arguments:
                arg = Optimist(job_id=job_uuid, arguments=item.arguments)
                session.add(arg)

            await session.commit()

            # Publish event
            rd = await get_redis()
            await publish_message(rd, STREAM_TASK_EVENTS, {
                "job_id": job_id_str,
                "event": "debate_completed"
            })
            logger.info(f"Debate completed for job {job_id_str}: {len(debate_output.skeptic_arguments)} skeptic, {len(debate_output.optimist_arguments)} optimist arguments saved.")
            return True