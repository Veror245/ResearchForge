import asyncio
import logging
from uuid import UUID
from redis.asyncio import Redis
from sqlalchemy import select
from backend.core.redis_client import (
    get_redis,
    ensure_consumer_group,
    STREAM_CLAIMS,
    STREAM_CRITIQUES,
    CRITIC_GROUP,
    publish_message,
)
from backend.core.database import async_session
from backend.models.claim_db import Claim          # SQLAlchemy Claim model
from backend.models.critic import Critique         # SQLAlchemy Critique model
from backend.agents.critic.agent import CritiqueAgent  # your CritiqueAgent class
from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)

class CritiqueConsumer:
    def __init__(self):
        self.agent = CritiqueAgent()

    async def run(self, consumer_id: str = "critic-1"):
        rd = await get_redis()
        await ensure_consumer_group(rd, STREAM_CLAIMS, CRITIC_GROUP)
        logger.info("Critic consumer started. Listening on research.claims")

        while True:
            try:
                messages = await rd.xreadgroup(
                    groupname=CRITIC_GROUP,
                    consumername=consumer_id,
                    streams={STREAM_CLAIMS: ">"},
                    count=1,
                    block=5000,
                )
                if not messages:
                    continue

                for stream_name, msg_list in messages:
                    for msg_id, fields in msg_list: # type: ignore
                        claim_id = fields.get("claim_id")
                        if not claim_id:
                            await rd.xack(STREAM_CLAIMS, CRITIC_GROUP, msg_id)
                            continue

                        success = await self.process_claim(claim_id)
                        if success:
                            await rd.xack(STREAM_CLAIMS, CRITIC_GROUP, msg_id)
                        else:
                            logger.error(f"Critique for claim {claim_id} failed, skipping.")
                            await rd.xack(STREAM_CLAIMS, CRITIC_GROUP, msg_id)
            except RedisTimeoutError:
                continue
            except Exception as e:
                logger.error(f"Consumer loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def process_claim(self, claim_id_str: str) -> bool:
        try:
            claim_uuid = UUID(claim_id_str)
        except ValueError:
            logger.error(f"Invalid claim UUID: {claim_id_str}")
            return False

        async with async_session() as session:
            claim = await session.get(Claim, claim_uuid)
            if not claim:
                logger.warning(f"Claim {claim_id_str} not found in DB")
                return False

            # Use the claim's text, evidence, and chunk (if available)
            claim_text = claim.text
            evidence = claim.evidence or ""
            chunk = claim.chunk or ""

            # Generate critiques
            critiques: list = await self.agent.generate_critiques(
                claim_text, evidence, chunk
            )

            if not critiques:
                logger.info(f"No critiques generated for claim {claim_id_str}")
                return True   # still ack, nothing to save

            # Persist critiques
            critique_ids = []
            for c in critiques:
                critique = Critique(
                    claim_id=claim_uuid,
                    task_id=claim.task_id,   # may be None             
                    critic_name=c.critic_name or "Research Critic",
                    critique_text=c.critique_text,
                    evidence=c.evidence,
                    score=c.score,
                    severity=c.severity.value if c.severity else "low",
                    chunk=chunk  # store the chunk text if available
                )
                session.add(critique)
                await session.flush()
                critique_ids.append(str(critique.id))

            await session.commit()

            # Publish each critique ID to the critiques stream
            rd = await get_redis()
            for cid in critique_ids:
                await publish_message(rd, STREAM_CRITIQUES, {"critique_id": cid})

            logger.info(f"Claim {claim_id_str}: {len(critiques)} critiques stored")
            return True