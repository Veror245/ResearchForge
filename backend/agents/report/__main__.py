import asyncio
import logging
from .consumer import ReportWriterConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

async def main():
    consumer = ReportWriterConsumer()
    await consumer.run()

if __name__ == "__main__":
    asyncio.run(main())