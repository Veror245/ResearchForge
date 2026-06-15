import asyncio
import logging
from .consumer import ResearchWorkerConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("worker_launcher")

async def main(num_workers: int = 3):
    logger.info(f"Launching {num_workers} worker consumers via asyncio...")
    tasks = []
    for i in range(num_workers):
        consumer = ResearchWorkerConsumer()
        consumer_task = consumer.run(consumer_id=f"worker-{i}")
        tasks.append(consumer_task)
    await asyncio.gather(*tasks) # type: ignore

if __name__ == "__main__":
    asyncio.run(main(num_workers=3))