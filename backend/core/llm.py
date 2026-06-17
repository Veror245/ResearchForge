from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
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

# claim_llm = ChatGroq(
#     model="llama-3.1-8b-instant",
#     temperature=0.0,
#     api_key=os.getenv("GROQ_API_KEY", "dummy"), # type: ignore
#     max_retries=3,
# )

# claim_llm = ChatOllama(
#     model="qwen3.5:4b",
#     temperature=0.0,
#     reasoning=False,
# )

claim_llm = ChatOpenAI(
    model="qwen3.5:4b",
    base_url="http://localhost:8080/v1",
    temperature=0.0,
    api_key=os.getenv("OLLAMA_API_KEY", "dummy"), # type: ignore
    max_retries=3,
)