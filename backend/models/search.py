from pydantic import BaseModel, HttpUrl
from typing import Optional

class SearchResult(BaseModel):
    title: str
    url: HttpUrl  # can use HttpUrl for strict validation if desired
    content: Optional[str] = ""
    engine: Optional[str] = ""