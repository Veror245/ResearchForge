import asyncio
import logging
from .consumer import ClaimExtractorConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

async def main():
    consumer = ClaimExtractorConsumer()
    await consumer.run(consumer_id="claim-extractor-1")

if __name__ == "__main__":
    asyncio.run(main())