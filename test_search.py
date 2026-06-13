import asyncio
from backend.services.search import SearchService

async def main():
    service = SearchService(engines=["google", "bing", "brave", "duckduckgo"])
    query = "open source voice cloning 2025"
    print(f"Searching for: {query}")
    results = await service.search(query, num_results=5)
    for i, r in enumerate(results, 1):
        print(f"{i}. {r.title}")
        print(f"   {r.url}")
        print(f"   snippet: {r.content[:100]}...") # type: ignore
        print()

if __name__ == "__main__":
    asyncio.run(main())