import asyncio
import logging
import signal
from .consumer import ResearchWorkerConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("worker_launcher")

async def main(num_workers: int = 3):
    shutdown_event = asyncio.Event()
    
    def handle_signal(sig):
        logger.info(f"Received signal {sig}, initiating graceful shutdown...")
        shutdown_event.set()
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
    
    # Start workers as proper Tasks
    worker_tasks = []
    for i in range(num_workers):
        consumer = ResearchWorkerConsumer()
        task = asyncio.create_task(
            consumer.run(consumer_id=f"worker-{i}", shutdown_event=shutdown_event)
        )
        worker_tasks.append(task)
    
    # Wait until shutdown is triggered
    await shutdown_event.wait()
    
    # Cancel all workers and wait for them to finish
    logger.info("Cancelling worker tasks...")
    for task in worker_tasks:
        task.cancel()
    
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    logger.info("All workers stopped cleanly.")

if __name__ == "__main__":
    asyncio.run(main(num_workers=3))