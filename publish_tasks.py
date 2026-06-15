import asyncio
from uuid import uuid4
from redis.asyncio import Redis
from backend.core.redis_client import get_redis, STREAM_TASKS, publish_message
from backend.core.database import async_session
from backend.models.research_task import ResearchTask
import backend.models

async def main():
    rd = await get_redis()

    queries = [
        "What are recent breakthroughs in AI for healthcare?",
        "Will open source voice cloning surpass commercial providers by 2030?",
        "What is the current state of quantum computing?",
    ]

    async with async_session() as session:
        for query in queries:
            task = ResearchTask(id=uuid4(), query=query, status="pending")
            session.add(task)
            await session.flush()
            task_id_str = str(task.id)
            # Publish to Redis stream
            await publish_message(rd, STREAM_TASKS, {
                "task_id": task_id_str,
                "query": query
            })
            print(f"Published task: {task_id_str} - {query}")
        await session.commit()

if __name__ == "__main__":
    asyncio.run(main())