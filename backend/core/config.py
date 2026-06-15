import os
from dotenv import load_dotenv

load_dotenv()  # loads .env from project root (when running from backend/)

class Settings:
    SEARXNG_BASE_URL: str = os.getenv("SEARXNG_BASE_URL", "http://localhost:8888")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://forge:forgepass@localhost:5432/researchforge")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    # other settings later

settings = Settings()