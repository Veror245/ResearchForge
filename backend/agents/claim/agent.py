from itertools import chain

from backend.models.claims import ClaimsResponse, ClaimType, Claim
from backend.models.research_finding import ResearchFinding
from backend.core.llm import claim_llm
from langchain_classic.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from chonkie import SentenceChunker
import json
import logging
from pydantic import ValidationError
import asyncio
import time

logger = logging.getLogger(__name__)

#TODO: fix llm speed
class ClaimExtraction:
    def __init__(self):
        self.llm = claim_llm
        self.chunker = SentenceChunker(
                tokenizer="character",     # Default tokenizer (or use "gpt2", etc.)
                chunk_size=2000,           # Maximum tokens per chunk
                chunk_overlap=100,         # Overlap between chunks
                min_sentences_per_chunk=5  # Minimum sentences in each chunk
            )
        self.claim_parser = PydanticOutputParser(pydantic_object=Claim)
        self.claims_response_parser = PydanticOutputParser(pydantic_object=ClaimsResponse)
        
        self.claim_extraction_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", """\
            You are a precise research analyst. Your job is to extract **claims** from a document.
            A claim is a factual statement that can be supported or refuted by evidence **present in the document**.

            For each claim you extract, you must provide:
            - `claim`: a concise, self‑contained sentence.
            - `evidence`: the **exact text** from the document that supports the claim. Use an empty string `""` only if the claim is an obvious inference but no explicit sentence exists.
            - `confidence`: 0.0–1.0. How directly does the evidence support the claim?
            - 1.0 = the text explicitly and unambiguously states the claim.
            - 0.7–0.9 = strong but not word‑for‑word.
            - 0.4–0.6 = reasonable inference, but not stated clearly.
            - 0.1–0.3 = weak hint or speculative.
            - 0.0 = no support at all (do not extract such claims).
            - `importance`: 0–10. How essential is this claim for understanding the document's main topic or argument? (10 = central conclusion, 1 = trivial side note).
            - `type`: classify the claim into one of these categories:
            - `fact`: a verifiable statement about reality (e.g., "The CPU has 8 cores").
            - `metric`: a numerical measurement or statistic (e.g., "Accuracy was 94%").
            - `decision`: a choice or design decision described in the text (e.g., "The team chose Python for prototyping").
            - `relationship`: a connection between two entities (e.g., "High temperature reduces battery life").
            - `requirement`: something that is mandated or needed (e.g., "The system must handle 1000 requests/sec").
            - `limitation`: a restriction, shortcoming, or boundary (e.g., "The model fails on non‑English input").

            Rules:
            - Only extract claims that are **explicitly present or directly inferable** from the text. Do not invent or assume.
            - If the document contains no factual claims, return an empty list `[]`.
            - The `evidence` field must always be a verbatim snippet from the text (not a paraphrase). If you cannot find the exact phrase, use `""` but lower your confidence.
            - Your response must be a single JSON object matching the ClaimsResponse schema.
            
            IMPORTANT: EXTRACT NO MORE THAN 5 CLAIMS. MAKE SURE THERE ARE ONLY 5 CLAIMS EXTRACTED MAXIMUM.

            {format_instructions}"""),
                    ("user", """Document:
            {document}

            Extract claims from the above document according to the instructions.""")
                ]
            ).partial(format_instructions=self.claims_response_parser.get_format_instructions())
        
        self.sem = asyncio.Semaphore(4)  # Limit concurrent LLM calls to 4

    def chunk_findings(self, markdown: str) -> list[str]:
        """
        Chunk the markdown content of a research finding into smaller pieces for processing.
        """
        chunks = self.chunker.chunk(markdown)
        result = [chunk.text for chunk in chunks]
        return result

    async def extract_claims_from_finding(self, finding: ResearchFinding) -> list[Claim]:
        """
        Extract claims from a single research finding.
        Splits the markdown into chunks, processes each chunk
        with the Titanium Fallback parsing strategy, and returns
        a combined list of valid Claims.
        """
        markdown_content = finding.markdown_content or ""
        if not markdown_content:
            return []

        chunks = self.chunk_findings(markdown_content)
        all_claims: list[Claim] = []
        chain = self.claim_extraction_prompt | self.llm

        for chunk_idx, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {chunk_idx + 1}/{len(chunks)}")
            try:
                # Call the LLM (with retry if you have a call_with_retry wrapper)
                raw_output = await self._call_llm(chain, {"document": chunk})
                content = raw_output.content.strip()
            except Exception as e:
                logger.error(f"Chunk {chunk_idx + 1}: LLM call failed: {e}")
                continue
            # if chunk_idx == 1:
            #     logger.warning("Reached chunk limit for testing. Stopping further processing.")
            #     break

            # Parse with Titanium Fallback
            claims_from_chunk = self._titanium_parse_claims(content)
            all_claims.extend(claims_from_chunk)
            logger.info(f"Chunk {chunk_idx + 1}: extracted {len(claims_from_chunk)} claims")
            # time.sleep(5)  # brief pause to respect rate limits, adjust as needed

        # Optional: deduplicate or filter globally here
        return all_claims

    async def _call_llm(self, chain, input_dict: dict):
        """
        Wrapper to call the chain asynchronously.
        Replace with your actual call_with_retry if available.
        """
        return await chain.ainvoke(input_dict)

    def _titanium_parse_claims(self, raw_content: str) -> list[Claim]:
        """
        Multi‑level parsing strategy (Titanium Fallback) for extracting
        a list of Claim objects from the LLM’s raw output.
        """
        # Pre‑clean common LLM artefacts
        content = raw_content.replace("```json", "").replace("```", "").strip()

        # ------------------ Level 1: Standard Pydantic Parser ------------------
        try:
            parsed = self.claims_response_parser.parse(content)
            return parsed.claims
        except Exception as e:
            logger.debug(f"Level 1 parsing failed: {e}")

        # ------------------ Level 2: Bracket Extraction ------------------
        try:
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            # If the LLM returned a pure array instead of the wrapper object
            if start_idx == -1 or end_idx == -1:
                start_idx = content.find("[")
                end_idx = content.rfind("]")
            if start_idx == -1 or end_idx == -1:
                raise ValueError("No JSON brackets found")

            json_str = content[start_idx : end_idx + 1]
            # Try parsing again with the trimmed string
            parsed = self.claims_response_parser.parse(json_str)
            logger.debug("Level 2 (bracket extraction) succeeded")
            return parsed.claims
        except Exception as e:
            logger.debug(f"Level 2 parsing failed: {e}")

        # ------------------ Level 3: Raw JSON Load & Manual Validation ------------------
        try:
            # At this point, we still have `json_str` from Level 2
            raw_dict = json.loads(json_str)  # may raise JSONDecodeError
            # Accept both {"claims": [...]} and a plain array [...]
            if isinstance(raw_dict, list):
                raw_claims = raw_dict
            elif isinstance(raw_dict, dict) and "claims" in raw_dict:
                raw_claims = raw_dict["claims"]
            else:
                raw_claims = []

            # Manually validate each claim, dropping invalid ones
            valid_claims = []
            for idx, item in enumerate(raw_claims):
                if not isinstance(item, dict):
                    continue
                try:
                    claim = Claim.model_validate(item)
                    valid_claims.append(claim)
                except ValidationError as val_err:
                    logger.warning(f"Level 3: invalid claim at index {idx}: {val_err}")
            logger.debug(f"Level 3 (raw load) succeeded, {len(valid_claims)} valid claims")
            return valid_claims
        except Exception as e:
            logger.warning(f"Level 3 (raw load) failed: {e}")

        # If everything fails, return an empty list
        return []
    
    async def extract_claims_from_finding_parallel(
        self,
        finding: ResearchFinding,
    ) -> list[Claim]:
        """
        Extract claims from a single research finding.

        Splits markdown into chunks, processes them in parallel,
        parses the outputs, and returns a combined list of claims.
        """

        markdown_content = finding.markdown_content or ""

        if not markdown_content:
            return []

        chunks = self.chunk_findings(markdown_content)

        logger.info(
            f"Created {len(chunks)} chunks"
        )

        chain = self.claim_extraction_prompt | self.llm

        async def process_chunk(
            chunk: str,
            chunk_idx: int,
        ) -> list[Claim]:

            logger.info(
                f"Processing chunk "
                f"{chunk_idx + 1}/{len(chunks)}"
            )

            try:
                async with self.sem:

                    raw_output = await self._call_llm(
                        chain,
                        {"document": chunk},
                    )

                content = raw_output.content.strip()

            except Exception as e:
                logger.error(
                    f"Chunk {chunk_idx + 1}: "
                    f"LLM call failed: {e}"
                )
                return []

            claims = self._titanium_parse_claims(
                content
            )

            logger.info(
                f"Chunk {chunk_idx + 1}: "
                f"extracted {len(claims)} claims"
            )

            return claims

        tasks = [
            process_chunk(chunk, idx)
            for idx, chunk in enumerate(chunks)
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        all_claims: list[Claim] = []

        for result in results:

            if isinstance(result, Exception):
                logger.error(
                    f"Task failed: {result}"
                )
                continue

            all_claims.extend(result) # type: ignore

        logger.info(
            f"Total extracted claims: "
            f"{len(all_claims)}"
        )

        return all_claims

        