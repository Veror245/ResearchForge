import asyncio
import redis.asyncio as redis

async def main():
    r = await redis.from_url("redis://localhost:6379")
    print(await r.ping())

asyncio.run(main())