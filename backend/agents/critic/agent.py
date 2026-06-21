import json

from jsonschema import ValidationError

from backend.models.critic import CritiqueSchema, Severity, CritiquesResponse
from backend.core.llm import critic_llm as llm
from langchain_core.prompts import ChatPromptTemplate
from langchain_classic.output_parsers import PydanticOutputParser
from typing import List
import logging

logger = logging.getLogger(__name__)

class CritiqueAgent:
    def __init__(self):
        self.llm = llm
        self.parser = PydanticOutputParser(pydantic_object=CritiquesResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                """
        You are an expert research critic responsible for evaluating the quality of research claims based on provided evidence.

        Your task is to analyze each claim and its supporting evidence, then provide a critique that includes:

        1. A clear and concise critique text that identifies strengths, weaknesses, gaps, or contradictions in the claim.
        2. An evidence-based rationale for your critique.
        3. A severity score (0.0 to 1.0) indicating the overall reliability of the claim based on the evidence.
        4. A severity level (low, medium, high, critical) based on the severity score.

        Guidelines for Critique:

        - Focus on the quality and reliability of the claim based on the evidence provided.
        - Identify any logical inconsistencies, unsupported assertions, or potential biases in the claim.
        - Consider the relevance and credibility of the evidence when formulating your critique.
        - Provide constructive feedback that could help improve the claim or guide further research.

        Severity Level Criteria:

        - LOW: Score < 0.25 - The claim is generally well-supported with minor issues.
        - MEDIUM: 0.25 ≤ Score < 0.5 - The claim has some significant weaknesses or gaps in evidence.
        - HIGH: 0.5 ≤ Score < 0.75 - The claim has major issues and is not well-supported by the evidence.
        - CRITICAL: Score ≥ 0.75 - The claim is fundamentally flawed or contradicted by strong evidence.

        Always provide a balanced critique that acknowledges any valid points while clearly identifying areas of concern.
        
        Output Format:
        {formatting_instructions}
                """
            ),
            (
                "user",
                """
        Claim: {claim_text}
        
        Evidence: {evidence_text}
        
        Chunk: {chunk_text}
                """
            )
        ]).partial(formatting_instructions=self.parser.get_format_instructions())

    
    async def generate_critiques(self, claim_text: str, evidence_text: str, chunk_text: str) -> List[CritiqueSchema]:
        chain = self.prompt | self.llm 
        input_dict = {"claim_text": claim_text, "evidence_text": evidence_text, "chunk_text": chunk_text}
        raw_output = await self._call_llm(chain, input_dict)
        content = raw_output.content
        critiques = self._titanium_parse_critiques(content)
        return critiques
    
    async def _call_llm(self, chain, input_dict: dict):
        """
        Wrapper to call the chain asynchronously.
        Replace with your actual call_with_retry if available.
        """
        return await chain.ainvoke(input_dict)
    
    
    def _titanium_parse_critiques(self, raw_content: str) -> list[CritiqueSchema]:
        """
        Multi‑level parsing strategy (Titanium Fallback) for extracting
        a list of CritiqueSchema objects from the LLM’s raw output.
        """
        content = raw_content.replace("```json", "").replace("```", "").strip()

        # ------------------ Level 1: Standard Pydantic Parser ------------------
        try:
            parsed = self.parser.parse(content)   # parser expects CritiquesResponse
            return parsed.critiques
        except Exception as e:
            logger.debug(f"Level 1 parsing failed: {e}")

        # ------------------ Level 2: Bracket Extraction ------------------
        try:
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            # If the LLM returned a plain array instead of the wrapper object
            if start_idx == -1 or end_idx == -1:
                start_idx = content.find("[")
                end_idx = content.rfind("]")
            if start_idx == -1 or end_idx == -1:
                raise ValueError("No JSON brackets found")
            json_str = content[start_idx : end_idx + 1]
            parsed = self.parser.parse(json_str)
            logger.debug("Level 2 (bracket extraction) succeeded")
            return parsed.critiques
        except Exception as e:
            logger.debug(f"Level 2 parsing failed: {e}")

        # ------------------ Level 3: Raw JSON Load & Manual Validation ------------------
        try:
            # Use json_str from Level 2 if available, otherwise whole content
            if 'json_str' not in locals():
                raw_data = json.loads(content)
            else:
                raw_data = json.loads(json_str)

            # Accept both {"critiques": [...]} and a plain array [...]
            if isinstance(raw_data, list):
                raw_critiques = raw_data
            elif isinstance(raw_data, dict) and "critiques" in raw_data:
                raw_critiques = raw_data["critiques"]
            else:
                raw_critiques = []

            valid_critiques = []
            for idx, item in enumerate(raw_critiques):
                if not isinstance(item, dict):
                    continue
                try:
                    critique = CritiqueSchema(**item)
                    valid_critiques.append(critique)
                except ValidationError as val_err:
                    logger.warning(f"Level 3: invalid critique at index {idx}: {val_err}")
            logger.debug(f"Level 3 (raw load) succeeded, {len(valid_critiques)} critiques")
            return valid_critiques
        except Exception as e:
            logger.warning(f"Level 3 (raw load) failed: {e}")

        return []