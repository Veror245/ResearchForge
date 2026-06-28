from jsonschema import ValidationError

from backend.core.llm import llm, claim_llm, critic_llm
from backend.models.debate import (
    Skeptic, 
    Optimist,
    SkepticSchema,
    OptimistSchema,
    SkepticalClaimsResponse,
    OptimisticClaimsResponse,
    DebateOutput
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_classic.output_parsers import PydanticOutputParser
import json
import logging

logger = logging.getLogger(__name__)

class DebateAgent:
    def __init__(self):
        self.llm = llm
        # We'll parse with two separate parsers and combine results
        self.skeptic_parser = PydanticOutputParser(pydantic_object=SkepticalClaimsResponse)
        self.optimist_parser = PydanticOutputParser(pydantic_object=OptimisticClaimsResponse)
        self.parser = PydanticOutputParser(pydantic_object=DebateOutput)
        # Actually, we can use the parser's format instructions
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """\
        You are a Principal Research Debater at a top‑tier analysis firm. Your job is to construct **two opposing, evidence‑based arguments** from the same set of claims and critiques, to help decision‑makers see a balanced picture.

        You will receive:
        - The original **research question**
        - A list of **extracted claims** (each with supporting evidence and confidence)
        - A list of **critiques** (each pointing out weaknesses or gaps in those claims)

        You must produce a JSON object with exactly two keys:
        - `skeptic_arguments` – arguments that **challenge or undermine** the research question
        - `optimist_arguments` – arguments that **support or strengthen** the research question

        Each key must contain an array of objects, and each object must have these fields:
        - `claim`: a concise summary of the claim or angle being addressed (1–2 sentences)
        - `evidence`: the most relevant piece(s) of source evidence, quoted or closely paraphrased (never invented)
        - `arguments`: a persuasive, logically sound point that clearly supports the corresponding stance (skeptical or optimistic). One idea per entry.

        **Critical rules:**
        - Derive **every** argument strictly from the provided claims and critiques. Do not bring in outside knowledge.
        - When a claim has a strong critique, use it for the skeptical side. When a claim has high confidence and no substantial critique, use it for the optimistic side.
        - Avoid repeating the same argument in different words. Each entry must add a distinct point.
        - Keep arguments concise (2–4 sentences) and professional, as if you are writing for a policy brief.
        - Never include markdown code fences in your response.
        - Output ONLY the JSON object described by the formatting instructions.

        {format_instructions}"""),
            ("user", """\
        Research Question:
        {query}

        Claims and Critiques:
        {claims_and_critiques}
        """)
        ]).partial(format_instructions=self.parser.get_format_instructions())


    async def generate_debate(self, query: str, claims: list, critiques: list) -> DebateOutput:
        # Format claims and critiques compactly
        lines = []
        for c in claims:
            lines.append(f"- Claim: {c.text}")
            if c.evidence:
                lines.append(f"  Evidence: {c.evidence[:200]}")
            # Find critiques for this claim (by claim_id)
            claim_critiques = [cr for cr in critiques if cr.claim_id == c.id]
            for cr in claim_critiques:
                lines.append(f"  Critique: {cr.critique_text[:200]}")
        claims_and_critiques = "\n".join(lines)
        
        logger.info(f"""Generating debate for query: {query} with {len(claims)} claims and {len(critiques)} 
                    critiques with {len(claims_and_critiques.split())} words in claims_and_critiques""")

        
        chain = self.prompt | self.llm
        response = await chain.ainvoke({"query": query, "claims_and_critiques": claims_and_critiques})
        raw = response.content

        return self._titanium_parse_debate(raw) # type: ignore

    def _titanium_parse_debate(self, content: str) -> DebateOutput:
        content = content.replace("```json", "").replace("```", "").strip()
        # Level 1: standard parse
        try:
            return self.parser.parse(content)
        except Exception:
            logger.debug("Level 1 failed")
        # Level 2: bracket extraction
        try:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                json_str = content[start:end+1]
                return self.parser.parse(json_str)
        except Exception:
            logger.debug("Level 2 failed")
        # Level 3: raw JSON load and manual construction
        try:
            data = json.loads(content)
            # Accept various shapes
            if isinstance(data, dict):
                skeptics = data.get("skeptic_arguments", [])
                optimists = data.get("optimist_arguments", [])
                # Try to validate each item manually
                def validate_items(items, schema_cls):
                    validated = []
                    for item in items:
                        if isinstance(item, dict):
                            try:
                                validated.append(schema_cls(**item))
                            except ValidationError:
                                pass
                    return validated
                skeptic_list = validate_items(skeptics, SkepticSchema)
                optimist_list = validate_items(optimists, OptimistSchema)
                return DebateOutput(skeptic_arguments=skeptic_list, optimist_arguments=optimist_list)
        except Exception as e:
            logger.error(f"Level 3 failed: {e}")
        # Return empty
        return DebateOutput(skeptic_arguments=[], optimist_arguments=[]) 