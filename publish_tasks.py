import asyncio
from uuid import uuid4, UUID
from sqlalchemy import select
from langchain_core.prompts import ChatPromptTemplate
from backend.core.redis_client import get_redis, STREAM_TASKS, publish_message
from backend.core.database import async_session
from backend.models.research_task import ResearchTask
from backend.models.claim_db import Claim
from backend.core.llm import llm
import backend.models

async def wait_for_tasks(task_ids: list[UUID], timeout: float = 300):
    elapsed = 0
    while elapsed < timeout:
        async with async_session() as session:
            stmt = select(ResearchTask.status).where(ResearchTask.id.in_(task_ids))
            result = await session.execute(stmt)
            statuses = [row[0] for row in result]
            if all(s in ("completed", "failed") for s in statuses):
                return
        await asyncio.sleep(1)
        elapsed += 1

async def wait_for_claims(task_id: UUID, timeout: float = 300):
    """Wait until at least one claim exists for the given task."""
    elapsed = 0
    while elapsed < timeout:
        async with async_session() as session:
            stmt = select(Claim).where(Claim.task_id == task_id)
            result = await session.execute(stmt)
            if result.scalars().first():
                return True
        await asyncio.sleep(1)
        elapsed += 1
    return False

async def main():
    rd = await get_redis()
    queries = [
        "What are the latest advancements in AI research?",
    ]

    task_ids = []
    async with async_session() as session:
        for query in queries:
            task = ResearchTask(id=uuid4(), query=query, status="pending")
            session.add(task)
            await session.flush()
            await session.commit()
            task_id_str = str(task.id)
            task_ids.append(task.id)
            await publish_message(rd, STREAM_TASKS, {"task_id": task_id_str, "query": query})
            print(f"Published task: {task_id_str} - {query}")
        await session.commit()

    print("\nWaiting for research to complete...")
    await wait_for_tasks(task_ids, timeout=300)

    print("Research completed. Waiting for claim extraction to finish...")
    for tid in task_ids:
        found = await wait_for_claims(tid, timeout=300)
        if not found:
            print(f"Warning: no claims found for task {tid} after timeout.")

    md = ""
    # Now fetch and print claims
    async with async_session() as session:
        for tid in task_ids:
            task = await session.get(ResearchTask, tid)
            if not task:
                continue
            print(f"\nTask: {task.query} (status: {task.status})")
            stmt = select(Claim).where(Claim.task_id == tid)
            result = await session.execute(stmt)
            claims = result.scalars().all()
            if not claims:
                print("  No claims extracted.")
                continue
            for i, claim in enumerate(claims, 1):
                md += f"Claim {claim.text}:\n"
                md += f"Evidence: {claim.evidence}\n"
                print(f"  Claim {i}:")
                print(f"    Text: {claim.text}")
                print(f"    Evidence: {(claim.evidence or '')[:200]}...")
                print(f"    Confidence: {claim.confidence:.2f}")
                print(f"    Importance: {claim.importance}")
                print(f"    Type: {claim.type}")
                print("    ---")
    print(len(md.split()) if md else "No markdown content for claims.")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a professional Research assistant. From the extracted claims, generate a detailed report about the topic you are asked to research.
         The report should be structured, clear, and concise. Use the claims and evidence to support your conclusions. 
         Avoid repeating the claims verbatim; instead, synthesize the information into a coherent narrative.
         Ensure that the report is informative and provides insights based on the claims and evidence provided."""),
        ("user", """Claims and Evidence:\n{claims}\n
         Query: {query}\n
         Please generate a detailed report based on the claims and evidence provided.""")
    ])
    response = await llm.ainvoke(prompt.invoke({"claims": md, "query": queries[0]}))
    print("\nGenerated Report:\n")
    print(response.content)

if __name__ == "__main__":
    asyncio.run(main())