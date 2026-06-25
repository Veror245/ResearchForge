from backend.core.llm import llm
from backend.models.research_task import ResearchTask, TaskStatus
from backend.models.research_job import ResearchJob, JobStatus
from pydantic import BaseModel, Field
from typing import List
from lanchain_core.prompts import ChatPromptTemplate


class Task(BaseModel):
    query: str
    


class Planner:
    def __init__(self):
        self.llm = llm

    async def plan(self, job: ResearchJob):
        # Implement the planning logic here
        # For example, you can generate a list of tasks based on the job's query
        tasks = []
        for i in range(5):  # Example: create 5 tasks
            task = ResearchTask(
                query=f"{job.query} - Task {i+1}",
                status=TaskStatus.PENDING,
                job_id=job.id
            )
            tasks.append(task)
        return tasks

if __name__ == "__main__":
    import asyncio
    from backend.core.database import async_session

    async def main():
        async with async_session() as session:
            # Create a new research job
            job = ResearchJob(query="Example research query")
            # session.add(job)
            # await session.commit()

            # Initialize the planner and plan tasks for the job
            planner = Planner()
            tasks = await planner.plan(job)

            # Add the generated tasks to the session and commit
            # session.add_all(tasks)
            # await session.commit()

            for t in tasks:
                print(f"Task: {t.query}, Status: {t.status}")
            print(f"Planned {len(tasks)} tasks for job {job.id}")

    asyncio.run(main())