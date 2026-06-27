import asyncio, logging
from .consumer import DebateConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

async def main():
    consumer = DebateConsumer()
    await consumer.run()
    
    

if __name__ == "__main__":
    asyncio.run(main())