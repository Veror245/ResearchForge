from backend.core.llm import llm
from backend.models.research_task import ResearchTask, TaskStatus
from backend.models.research_job import ResearchJob, JobStatus
from pydantic import BaseModel, Field
from typing import List
from langchain_core.prompts import ChatPromptTemplate
from langchain_classic.output_parsers import PydanticOutputParser
import json
import logging
from backend.core.redis_client import publish_log, get_redis, STREAM_LOGS

logger = logging.getLogger(__name__)


class PlannerOutput(BaseModel):
    sub_queries: list[str] = Field(
        description="Exactly 3 web‑searchable sub‑queries that together cover the original question from different angles",
        min_length=3,
        max_length=3
    )
    


class Planner:
    def __init__(self):
        self.llm = llm
        
        self.parser = PydanticOutputParser(pydantic_object=PlannerOutput)
        self.prompt = ChatPromptTemplate.from_messages([
                (
                    "system",
                    """You are a senior research strategist. Your only job is to break a complex research question into exactly three focused, web‑searchable sub‑queries.

            Each sub‑query must:
            - Be a self‑contained question or search phrase.
            - Cover a distinct aspect of the original question (e.g., technical, economic, regulatory, historical, or counter‑argument).
            - Be concise but specific enough to retrieve high‑quality evidence from a general web search.
            - Avoid unnecessary overlap with the other sub‑queries.

            {formatting_instructions}

            Return ONLY the JSON object described in the formatting instructions. Do not include any additional text, commentary, or markdown fences."""
                ),
                (
                    "user",
                    "Research question: {query}"
                )
            ]).partial(formatting_instructions=self.parser.get_format_instructions())

    async def plan(self, job: ResearchJob) -> PlannerOutput:
        """
        Breaks a research job's query into exactly three focused sub‑queries.

        Args:
            job (ResearchJob): The research job containing the original query.

        Returns:
            PlannerOutput: A PlannerOutput object containing the three sub‑queries.
        """
        self.redis = await get_redis()
        chain = self.prompt | self.llm
        input = {"query": job.query}
        raw_response = await self._call_llm(chain, input)
        response = self._titanium_parse_planner(raw_response)
        await publish_log(self.redis, str(job.id), "planner", f"Generated sub-queries: {response.sub_queries}")
        return response
        
   
    async def _call_llm(self, chain, input: dict):
        response = await chain.ainvoke(input)
        return response.content
    
    def _titanium_parse_planner(self, raw_content: str) -> PlannerOutput:
        content = raw_content.replace("```json", "").replace("```", "").strip()

        # ------------------ Level 1: Standard Pydantic Parser ------------------
        try:
            return self.parser.parse(content)
        except Exception as e:
            logger.debug(f"Level 1 parsing failed: {e}")

        # ------------------ Level 2: Bracket Extraction ------------------
        try:
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            if start_idx == -1 or end_idx == -1:
                raise ValueError("No JSON brackets found")
            json_str = content[start_idx : end_idx + 1]
            return self.parser.parse(json_str)
        except Exception as e:
            logger.debug(f"Level 2 parsing failed: {e}")

        # ------------------ Level 3: Raw JSON Load & Manual Construction ------------------
        try:
            if 'json_str' not in locals():
                raw_data = json.loads(content)
            else:
                raw_data = json.loads(json_str)

            # Extract sub_queries from various shapes
            sub_queries = []
            if isinstance(raw_data, list):
                sub_queries = [str(item) for item in raw_data if isinstance(item, str)]
            elif isinstance(raw_data, dict):
                maybe_list = raw_data.get("sub_queries", raw_data.get("queries", []))
                if isinstance(maybe_list, list):
                    sub_queries = [str(q) for q in maybe_list if isinstance(q, str)]
                elif isinstance(maybe_list, str):
                    sub_queries = [maybe_list]
            if len(sub_queries) < 3:
                # Pad or trim to exactly 3 if needed (optional, depending on strictness)
                pass
            # Construct a PlannerOutput object
            planner_output = PlannerOutput(sub_queries=sub_queries[:3])  # at most 3
            return planner_output
        except Exception as e:
            logger.warning(f"Level 3 (raw load) failed: {e}")

        # Final fallback: empty output
        return PlannerOutput(sub_queries=[])

if __name__ == "__main__":
    import asyncio
    from backend.core.database import async_session

    # async def main():
    #     async with async_session() as session:
    #         # Create a new research job
    #         job = ResearchJob(query="Example research query")
    #         # session.add(job)
    #         # await session.commit()

    #         # Initialize the planner and plan tasks for the job
    #         planner = Planner()
    #         tasks = await planner.plan(job)

    #         # Add the generated tasks to the session and commit
    #         # session.add_all(tasks)
    #         # await session.commit()

    #         for t in tasks:
    #             print(f"Task: {t.query}, Status: {t.status}")
    #         print(f"Planned {len(tasks)} tasks for job {job.id}")

    # asyncio.run(main())