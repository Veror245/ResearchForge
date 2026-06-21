import json

from langchain_core.prompts import ChatPromptTemplate
from backend.core.llm import llm
from backend.models.report import ReportSchema
from langchain_classic.output_parsers import PydanticOutputParser
from typing import Optional
import logging


logger = logging.getLogger(__name__)

class ReportGenerator:
    def __init__(self):
        
        self.llm = llm
        self.parser = PydanticOutputParser(pydantic_object=ReportSchema)
        
        self.prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                """
        You are a senior research analyst responsible for producing high-quality intelligence reports.

        Your task is to synthesize evidence from extracted claims into a professional research report.

        Guidelines:

        1. Analyze and synthesize information rather than listing claims.
        2. Group related findings into logical themes.
        3. Resolve contradictions when possible and explicitly mention disagreements in evidence.
        4. Prioritize evidence-supported conclusions.
        5. Avoid repeating the source claims verbatim.
        6. Distinguish between:
        - Verified findings
        - Strong indications
        - Speculative or uncertain information
        7. Highlight patterns, trends, risks, opportunities, and implications.
        8. Maintain an objective and evidence-based tone.
        9. Do not invent facts that are not supported by the provided evidence.
        10. Write as if the report will be reviewed by decision-makers.

        Markdown Formatting Rules (must be followed exactly):

        - Write in **plain paragraphs** with no manual line breaks.
        - Do **not** press Enter to wrap text at a certain width. Let the text flow naturally.
        - Use **numbered lists** only as: `1.`, `2.`, etc., each on a new line.
        - Use **bullet lists** only as: `- ` (hyphen + space), each on a new line.
        - Never use special bullet characters like `•`, `◦`, `▪`. These are forbidden.
        - A blank line must separate paragraphs and list blocks.

        Example of a CORRECT list:

        1. This is the first finding. It can span multiple lines, but the text is continuous.
        2. This is the second finding.
        3. Third finding.

        Example of an INCORRECT approach (DO NOT DO THIS):
        • First item • Second item   ← wrong bullet, wrong line breaks

        Output Structure:
        {formatting_instructions}
        """
            ),
            (
                "user",
                """
        Research Query:
        {query}

        Claims and Evidence:
        {claims}

        Generate a comprehensive research report.
        """
            )
        ]).partial(formatting_instructions=self.parser.get_format_instructions())
        
        

    async def generate_report(self, findings: str, query: str, claims: Optional[str] = None, evidence: Optional[str] = None) -> ReportSchema:
        chain = self.prompt | self.llm
        inp = {"claims": findings, "query": query}
        response = await self._call_llm(chain, inp)
        
        cleaned_report = self._titanium_parse_report(response.content)
        return cleaned_report
    
    async def _call_llm(self, chain, input_dict: dict):
        """
        Wrapper to call the chain asynchronously.
        Replace with your actual call_with_retry if available.
        """
        return await chain.ainvoke(input_dict)

    def _titanium_parse_report(self, raw_content: str) -> ReportSchema:
        """
        Multi‑level parsing strategy (Titanium Fallback) for extracting
        a ReportSchema object from the LLM’s raw output.
        """
        # Pre‑clean common LLM artefacts
        content = raw_content.replace("```json", "").replace("```", "").strip()

        # ------------------ Level 1: Standard Pydantic Parser ------------------
        try:
            parsed = self.parser.parse(content)
            return parsed
        except Exception as e:
            logger.debug(f"Level 1 parsing failed: {e}")

        # ------------------ Level 2: Bracket Extraction ------------------
        try:
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            # The report is always an object, so we only need { ... }
            if start_idx == -1 or end_idx == -1:
                raise ValueError("No JSON brackets found")
            json_str = content[start_idx : end_idx + 1]
            # Try parsing with the trimmed string
            parsed = self.parser.parse(json_str)
            logger.debug("Level 2 (bracket extraction) succeeded")
            return parsed
        except Exception as e:
            logger.debug(f"Level 2 parsing failed: {e}")

        # ------------------ Level 3: Raw JSON Load & Manual Construction ------------------
        try:
            # We'll use json_str from Level 2 if available, otherwise fallback to the whole content
            if 'json_str' not in locals():
                # last resort: try to load the entire content
                raw_dict = json.loads(content)
            else:
                raw_dict = json.loads(json_str)

            # Build the ReportSchema manually, dropping any extra keys and filling defaults
            report = ReportSchema(
                executive_summary=raw_dict.get("executive_summary", ""),
                key_findings=raw_dict.get("key_findings", []),
                methodology=raw_dict.get("methodology", ""),
                supporting_evidence=raw_dict.get("supporting_evidence", []),
                final_assessment=raw_dict.get("final_assessment", ""),
            )
            logger.debug("Level 3 (raw load) succeeded")
            return report
        except Exception as e:
            logger.warning(f"Level 3 (raw load) failed: {e}")

        # If everything fails, return an empty default report
        return ReportSchema(executive_summary="Report generation failed.") # type: ignore