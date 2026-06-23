# import asyncio
# import logging
# import time
# from uuid import UUID
# from redis.asyncio import Redis
# from sqlalchemy import select
# from backend.core.redis_client import (
#     get_redis,
#     ensure_consumer_group,
#     STREAM_CLAIMS,
#     STREAM_CRITIQUES,
#     CRITIC_GROUP,
#     publish_message,
# )
# from backend.core.database import async_session
# from backend.models.claim_db import Claim          # SQLAlchemy Claim model
# from backend.models.critic import Critique         # SQLAlchemy Critique model
# from backend.agents.critic.agent import CritiqueAgent  # your CritiqueAgent class
# from redis.exceptions import TimeoutError as RedisTimeoutError

# logger = logging.getLogger(__name__)

# class CritiqueConsumer:
#     def __init__(self):
#         self.agent = CritiqueAgent()

#     async def run(self, consumer_id: str = "critic-1"):
#         rd = await get_redis()
#         await ensure_consumer_group(rd, STREAM_CLAIMS, CRITIC_GROUP)
#         logger.info("Critic consumer started. Listening on research.claims")

#         while True:
#             try:
#                 messages = await rd.xreadgroup(
#                     groupname=CRITIC_GROUP,
#                     consumername=consumer_id,
#                     streams={STREAM_CLAIMS: ">"},
#                     count=1,
#                     block=5000,
#                 )
#                 if not messages:
#                     continue

#                 for stream_name, msg_list in messages:
#                     for msg_id, fields in msg_list: # type: ignore
#                         claim_id = fields.get("claim_id")
#                         if not claim_id:
#                             await rd.xack(STREAM_CLAIMS, CRITIC_GROUP, msg_id)
#                             continue

#                         success = await self.process_claim(claim_id)
#                         if success:
#                             await rd.xack(STREAM_CLAIMS, CRITIC_GROUP, msg_id)
#                         else:
#                             logger.error(f"Critique for claim {claim_id} failed, skipping.")
#                             await rd.xack(STREAM_CLAIMS, CRITIC_GROUP, msg_id)
#             except RedisTimeoutError:
#                 continue
#             except Exception as e:
#                 logger.error(f"Consumer loop error: {e}", exc_info=True)
#                 await asyncio.sleep(1)

#     async def process_claim(self, claim_id_str: str) -> bool:
#         try:
#             claim_uuid = UUID(claim_id_str)
#         except ValueError:
#             logger.error(f"Invalid claim UUID: {claim_id_str}")
#             return False

#         async with async_session() as session:
#             claim = await session.get(Claim, claim_uuid)
#             if not claim:
#                 logger.warning(f"Claim {claim_id_str} not found in DB")
#                 return False

#             # Use the claim's text, evidence, and chunk (if available)
#             claim_text = claim.text
#             evidence = claim.evidence or ""
#             chunk = claim.chunk or ""

#             input = {
#                 "claim_text": claim_text,
#                 "evidence_text": evidence,
#                 "chunk_text": chunk,
#                 "query": claim.task.query if claim.task else ""
#             }
#             # Generate critiques
#             # critiques: list = await self.agent.generate_critiques(
#             #     claim_text, evidence, chunk, claim.task.query if claim.task else ""
#             # )
            
#             critiques: list = await self.agent.parallel_critique(input=[input])  # Use parallel critique for better performance
            
#             t0 = time.time()
#             if not critiques:
#                 logger.info(f"No critiques generated for claim {claim_id_str}")
#                 return True   # still ack, nothing to save
#             logger.info(f"Critiques generated for claim {claim_id_str} in {time.time() - t0:.2f}s")
            
#             # Persist critiques
#             critique_ids = []
#             for c in critiques:
#                 critique = Critique(
#                     claim_id=claim_uuid,
#                     task_id=claim.task_id,   # may be None             
#                     critic_name=c.critic_name or "Research Critic",
#                     critique_text=c.critique_text,
#                     evidence=c.evidence,
#                     score=c.score,
#                     severity=c.severity.value if c.severity else "low",
#                     chunk=chunk  # store the chunk text if available
#                 )
#                 session.add(critique)
#                 await session.flush()
#                 critique_ids.append(str(critique.id))

#             await session.commit()

#             # Publish each critique ID to the critiques stream
#             rd = await get_redis()
#             for cid in critique_ids:
#                 await publish_message(rd, STREAM_CRITIQUES, {"critique_id": cid})

#             logger.info(f"Claim {claim_id_str}: {len(critiques)} critiques stored")
#             return True



import asyncio, logging, time
from uuid import UUID
from redis.asyncio import Redis
from sqlalchemy import select
from backend.core.redis_client import (
    get_redis,
    ensure_consumer_group,
    STREAM_TASK_READY,            # <-- now listens to task ready
    STREAM_CRITIQUES,
    CRITIC_GROUP,
    STREAM_TASK_EVENTS,
    publish_message,
)
from backend.core.database import async_session
from backend.models.research_task import ResearchTask
from backend.models.claim_db import Claim
from backend.models.critic import Critique
from backend.agents.critic.agent import CritiqueAgent
from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)
   # separate from report writer group

class CritiqueConsumer:
    def __init__(self):
        self.agent = CritiqueAgent()

    async def run(self, consumer_id: str = "critic-task-1"):
        rd = await get_redis()
        await ensure_consumer_group(rd, STREAM_TASK_EVENTS, CRITIC_GROUP)
        logger.info("Critic (task-level) started. Listening on research.task_ready")

        while True:
            try:
                messages = await rd.xreadgroup(
                    groupname=CRITIC_GROUP,
                    consumername=consumer_id,
                    streams={STREAM_TASK_EVENTS: ">"},
                    count=1,
                    block=5000,
                )
                if not messages:
                    continue

                for stream_name, msg_list in messages:
                    for msg_id, fields in msg_list:  # type: ignore
                        if fields.get("event") != "claims_completed":
                            await rd.xack(STREAM_TASK_EVENTS, CRITIC_GROUP, msg_id)
                            continue
                        task_id = fields.get("task_id")
                        if not task_id:
                            await rd.xack(STREAM_TASK_EVENTS, CRITIC_GROUP, msg_id)
                            continue

                        success = await self.process_task(task_id)
                        if success:
                            await rd.xack(STREAM_TASK_EVENTS, CRITIC_GROUP, msg_id)
                        else:
                            logger.error(f"Task {task_id} critique failed, acking anyway.")
                            await rd.xack(STREAM_TASK_EVENTS, CRITIC_GROUP, msg_id)
            except RedisTimeoutError:
                continue
            except Exception as e:
                logger.error(f"Consumer loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def wait_for_claims(self, task_uuid: UUID, timeout: float = 60) -> list[Claim]:
        """Wait until claims exist for this task, then return them."""
        elapsed = 0
        async with async_session() as session:
            while elapsed < timeout:
                stmt = select(Claim).where(Claim.task_id == task_uuid)
                result = await session.execute(stmt)
                claims = result.scalars().all()
                if claims:
                    return list(claims)
                await asyncio.sleep(1)
                elapsed += 1
        return []

    async def process_task(self, task_id_str: str) -> bool:
        try:
            task_uuid = UUID(task_id_str)
        except ValueError:
            logger.error(f"Invalid task UUID: {task_id_str}")
            return False

        # Wait for claims to be extracted
        claims = await self.wait_for_claims(task_uuid, timeout=5)
        claims = claims[:10]
        if not claims:
            logger.warning(f"No claims found for task {task_id_str} after waiting")
            return False

        # Prepare input dicts for all claims
        claim_inputs = []
        for claim in claims:
            claim_inputs.append({
                "claim_text": claim.text,
                "evidence_text": claim.evidence or "",
                "chunk_text": claim.chunk or "",
                "query": "",  # optional, you can fetch task.query later
            })

        t0 = time.time()
        # Process all claims in parallel (semaphore limits concurrency)
        results_per_claim = await self.agent.parallel_critique(claim_inputs)
        logger.info(f"Task {task_id_str}: parallel critique finished in {time.time() - t0:.2f}s")

        # Persist critiques
        async with async_session() as session:
            for claim, critique_list in zip(claims, results_per_claim):
                if not critique_list:
                    continue
                # Normalize to a list of CritiqueSchema instances
                if isinstance(critique_list, tuple):
                    critique_list = list(critique_list)

                for crit_data in critique_list:
                    # If the LLM returned a dict (from fallback parsing), convert it
                    if isinstance(crit_data, dict):
                        try:
                            crit_data = CritiqueSchema(**crit_data)
                        except Exception:
                            logger.warning("Invalid critique dict, skipping")
                            continue
                    # Now crit_data should be a CritiqueSchema instance
                    if not hasattr(crit_data, 'critique_text'):
                        logger.warning(f"Unexpected critique type: {type(crit_data)}, skipping")
                        continue

                    critique = Critique(
                        claim_id=claim.id,
                        task_id=task_uuid,
                        critic_name=crit_data.critic_name or "Research Critic",
                        critique_text=crit_data.critique_text,
                        evidence=crit_data.evidence,
                        score=crit_data.score,
                        severity=crit_data.severity.value if hasattr(crit_data.severity, 'value') else str(crit_data.severity or "low"),
                    )
                    session.add(critique)
            logger.info(f"Task {task_id_str}: saved critiques for {len(claims)} claims")

        rd = await get_redis()
        await publish_message(rd, STREAM_TASK_EVENTS, {
                "task_id": task_id_str,
                "event": "critiques_completed"
            })
        return True