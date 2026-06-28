from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
# from ...publish_tasks import *
import publish_tasks

root = Path(__file__).parent.parent.parent



app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def start():
    return {"message": "ResearchForge API is running."}

@app.post("/research")
async def research(queries: list[str]):
    # Placeholder for research logic
    raw_md, html_full = await publish_tasks.main(queries=queries) # type: ignore
    return {"message": "Research initiated.", "queries": queries, "raw_md": raw_md, "html_full": html_full}
