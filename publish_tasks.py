import asyncio
from uuid import uuid4, UUID
from redis.asyncio import Redis
from backend.core.redis_client import get_redis, STREAM_TASKS, publish_message
from backend.core.database import async_session
from backend.models.research_task import ResearchTask
from backend.models.claim_db import Claim         # SQLAlchemy Claim model
import backend.models                          # ensure all models loaded

async def wait_for_tasks(task_ids: list[UUID], timeout: float = 500):
    """Wait until all tasks are no longer pending/running, then return."""
    async with async_session() as session:
        elapsed = 0
        while elapsed < timeout:
            # Fetch current status of each task
            tasks = []
            for tid in task_ids:
                t = await session.get(ResearchTask, tid)
                tasks.append(t)
            # If all tasks are finished (not pending or running), break
            if all(t and t.status in ("completed", "failed") for t in tasks):
                return
            await asyncio.sleep(1)
            elapsed += 1
        # Timeout reached – proceed anyway

async def main():
    rd = await get_redis()

    queries = [
        # "What are recent breakthroughs in AI for healthcare?",
        "Will open source voice cloning surpass commercial providers by 2030?",
        # "What is the current state of quantum computing?",
    ]

    task_ids = []
    async with async_session() as session:
        for query in queries:
            task = ResearchTask(id=uuid4(), query=query, status="pending")
            session.add(task)
            await session.flush()
            task_id_str = str(task.id)
            task_ids.append(task.id)
            # Publish to Redis stream
            await publish_message(rd, STREAM_TASKS, {
                "task_id": task_id_str,
                "query": query
            })
            print(f"Published task: {task_id_str} - {query}")
        await session.commit()

    print("\nWaiting for tasks to complete (research + claim extraction)...")
    await wait_for_tasks(task_ids, timeout=500)

    # Fetch and print claims for all tasks
    async with async_session() as session:
        for tid in task_ids:
            task = await session.get(ResearchTask, tid)
            if not task:
                print(f"Task {tid} not found in DB.")
                continue
            print(f"\nTask: {task.query} (status: {task.status})")
            # Query claims with this task_id (assuming claim.task_id is used)
            from sqlalchemy import select
            stmt = select(Claim).where(Claim.task_id == tid)
            result = await session.execute(stmt)
            claims = result.scalars().all()
            if not claims:
                print("  No claims extracted for this task.")
                continue
            for i, claim in enumerate(claims, 1):
                print(f"  Claim {i}:")
                print(f"    Text: {claim.text}")
                print(f"    Evidence: {(claim.evidence or '')[:200]}...")
                print(f"    Confidence: {claim.confidence:.2f}")
                print(f"    Importance: {claim.importance}")
                print(f"    Type: {claim.type}")
                print("    ---")

if __name__ == "__main__":
    asyncio.run(main())