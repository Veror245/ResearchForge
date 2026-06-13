import os
from dotenv import load_dotenv

load_dotenv()  # loads .env from project root (when running from backend/)

class Settings:
    SEARXNG_BASE_URL: str = os.getenv("SEARXNG_BASE_URL", "http://localhost:8888")
    # other settings later

settings = Settings()