import asyncio
import logging
import sys
from sqlalchemy import select, func
from backend.core.database import async_session
from backend.models.research_finding import ResearchFinding
from backend.agents.claim.agent import ClaimExtraction
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    # Fetch a random finding that has markdown_content
    async with async_session() as session:
        stmt = (
            select(ResearchFinding)
            .where(ResearchFinding.markdown_content.isnot(None)).where(ResearchFinding.id != "812dcbe6-6675-4bc4-9fc7-7f54b9b37d88")
            .order_by(func.random())
            .limit(1)
        )
        
        
        result = await session.execute(stmt)
        finding = result.scalar_one_or_none()

        if not finding:
            logger.error("No findings with markdown_content found. Run the research worker first.")
            return

        logger.info(f"Testing extraction on finding: {finding.id}")
        logger.info(f"URL: {finding.url}")
        logger.info(f"Markdown length: {len(finding.markdown_content)} chars") # type: ignore #

    # Instantiate the ClaimExtractor
    extractor = ClaimExtraction()  # Uses default LLM from get_llm()

    # t0 = time.time()
    # # Run extraction
    # claims = await extractor.extract_claims_from_finding(finding)
    # print(f"Extraction completed in {time.time() - t0:.2f} seconds.")
    
    print(finding.query)
    t0 = time.time()
    claims = await extractor.extract_claims_from_finding_parallel(finding, query=finding.query)  # Pass the query to the parallel extraction
    print(f"Parallel extraction completed in {time.time() - t0:.2f} seconds.")

    #Print results
    print(f"\n✅ Extracted {len(claims)} claims:\n")
    for i, claim in enumerate(claims, 1):
        print(f"Claim {i}:")
        print(f"  Text: {claim.claim}")
        print(f"  Evidence: {claim.evidence[:200]}...")
        print(f" Evidence length: {len(claim.evidence.split())} words")
        print(f"  Confidence: {claim.confidence:.2f}")
        print(f"  Importance: {claim.importance}")
        print(f"  Type: {claim.type.value}")
        print("-" * 60)

if __name__ == "__main__":
    asyncio.run(main())