from typing import List, Optional
import httpx
from backend.core.config import settings
from pydantic import BaseModel, HttpUrl
from backend.models.search import SearchResult

    
class SearchService:
    def __init__(self, base_url: Optional[str] = None,  engines: Optional[List[str]] = None,):
        self.base_url = base_url or settings.SEARXNG_BASE_URL
        self.search_url = f"{self.base_url}/search"
        self.engines = engines

    async def search(
        self,
        query: str,
        num_results: int = 10,
        timeout: float = 10.0,
    ) -> List[SearchResult]:
        params = {
            "q": query,
            "format": "json",
            "pageno": 1,
            "language": "en",
            "safesearch": 0,
        }
        if self.engines:
            params["engines"] = ",".join(self.engines)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(self.search_url, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("results", [])[:num_results]:
            result = SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=item.get("content", ""),
                engine=item.get("engine", ""),
            )
            results.append(result)
        return results