from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file

llm = ChatOpenAI(
    model="gemma4:31b-cloud",  # Swap to your preferred local model if needed
    temperature=0.0,
    api_key=os.getenv("OLLAMA_API_KEY", "dummy"), # type: ignore
    base_url="https://ollama.com/v1",
    max_retries=3
)

claim_llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.0,
    api_key=os.getenv("GROQ_API_KEY", "dummy"), # type: ignore
    max_retries=3,
)