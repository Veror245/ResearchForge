# ResearchForge

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/)

ResearchForge is an autonomous multi-agent research platform. A user asks a question, the system breaks it into focused sub-queries, searches the web through SearXNG, crawls and normalizes source pages, extracts claims from the evidence, critiques those claims, debates competing interpretations, and assembles a fully referenced Markdown and PDF report with a confidence score.

## What It Does

ResearchForge runs as an event-driven pipeline built on Redis Streams. Each stage consumes a stream event, performs its work independently, and emits the next event when it completes. The system is designed to behave like a compact research organization rather than a single-step summarizer, with separate agents handling planning, retrieval, synthesis, critique, and final reporting.

The generated report includes:

- Executive summary
- Key findings
- Methodology
- Supporting evidence
- Counterarguments
- Final assessment
- Confidence score

## Features

- Autonomous multi-agent research pipeline
- Event-driven orchestration with Redis Streams
- Parallel web search and crawling across multiple workers
- Claim extraction with evidence-backed critique
- Multi-agent debate for balanced, adversarial analysis
- Markdown and PDF report generation with polished formatting
- Confidence scoring for final conclusions
- REST API and Streamlit interface for job submission and monitoring
- Live progress visibility through job and log endpoints
- Pluggable LLM backends through the existing core configuration layer

## Architecture

```mermaid
flowchart LR
    subgraph Frontend
        UI[Streamlit UI]
    end

    subgraph Backend
        API[FastAPI API]
        RS[(Redis Streams)]
        P[Planner Agent]
        RW[Research Workers<br/>3x parallel]
        C[Claim Extractor]
        K[Critic Agent]
        D[Debate Agent]
        R[Report Writer]
        DB[(PostgreSQL<br/>pgvector)]
    end

    subgraph External
        SX[SearXNG<br/>self-hosted]
        CA[Crawl4AI<br/>crawler]
        EM[SentenceTransformers<br/>embeddings]
    end

    UI --> API
    API -->|publish job| RS

    RS -->|job_researched| C
    RS -->|claims_completed| K
    RS -->|critiques_completed| D
    RS -->|debate_completed| R
    RS -->|research_completed| P
    P -->|publish tasks| RS

    RS -->|research tasks| RW
    RW -->|search| SX
    RW -->|crawl| CA
    RW -->|deduplicate / MMR| EM

    RW -->|save findings| DB
    C -->|save claims| DB
    K -->|save critiques| DB
    D -->|save arguments| DB
    R -->|save report| DB
    R -->|markdown| API

    DB ---|read| UI
    API ---|REST| UI
```

The FastAPI application is defined in [backend/api/main.py](backend/api/main.py), and the Streamlit frontend is in [frontend/app.py](frontend/app.py).

## Tech Stack

- Backend: FastAPI, LangChain, LangGraph
- Messaging: Redis Streams via `redis-py`
- Database: PostgreSQL with pgvector
- Search: Self-hosted SearXNG
- Crawling: Crawl4AI
- LLMs: OpenAI-compatible clients, Groq, and Ollama integrations
- Embeddings: SentenceTransformers
- Frontend: Streamlit
- PDF generation: Markdown + WeasyPrint
- Package management: uv

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Playwright browser binaries for Crawl4AI
- Service credentials or endpoints configured in [backend/core/llm.py](backend/core/llm.py)

## Installation

1. Start the infrastructure services.

```bash
docker compose up -d
```

This starts PostgreSQL with pgvector, Redis, and SearXNG.

2. Install the Python environment.

```bash
uv sync
```

If Crawl4AI needs browser binaries in your environment, install them with:

```bash
uv run playwright install --with-deps
```

3. Configure environment variables.

Create a `.env` file in the project root. At minimum, set the service URLs used by the app:

```env
DATABASE_URL=postgresql+asyncpg://forge:forgepass@localhost:5432/researchforge
REDIS_URL=redis://localhost:6379
SEARXNG_BASE_URL=http://localhost:8888
```

Add the provider credentials required by your LLM configuration in [backend/core/llm.py](backend/core/llm.py).

4. Initialise the database.

```bash
uv run python init_db.py
```

## Running The App

Start the worker processes first:

```bash
uv run python services_launcher.py
```

This launches the planner, research, claim, critic, debate, and report workers.

Start the API in a separate terminal:

```bash
uv run uvicorn backend.api.main:app --reload --port 8000
```

Start the Streamlit frontend in another terminal:

```bash
uv run streamlit run frontend/app.py
```

Then open http://localhost:8501 in your browser.

## Command-Line Run

You can also submit a research question from the terminal:

```bash
uv run python publish_tasks.py "Your research question here"
```

This publishes the job to Redis, waits for the pipeline to finish, and writes the PDF report to `data/report_<question>.pdf`.

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/` | Health check |
| POST | `/research` | Create a new research job |
| GET | `/job/{job_id}/status` | Check job status |
| GET | `/job/{job_id}/report` | Get the structured report as JSON |
| GET | `/job/{job_id}/report/markdown` | Get the cleaned Markdown report |
| GET | `/job/{job_id}/report/pdf` | Download the rendered PDF report |

## Project Layout

```text
backend/
  api/        FastAPI application and routes
  agents/     Planner, research, claim, critic, debate, gap, and report agents
  core/       Configuration, database, Redis, and LLM setup
  models/     SQLAlchemy models for jobs, claims, critiques, reports, and related data
  services/   Search service wrappers
frontend/
  app.py      Streamlit dashboard
init_db.py    Database bootstrap script
publish_tasks.py    CLI helper for submitting a query from the terminal
services_launcher.py Worker launcher for the main agents
docker-compose.yml   PostgreSQL, Redis, and SearXNG services
```

## Notes

- Research workers use the SearXNG instance configured by `SEARXNG_BASE_URL`.
- The PDF export is generated from the Markdown report and includes the confidence score.
- The dashboard shows live agent logs while the job is running, then renders the final report and PDF download.

## License

MIT
