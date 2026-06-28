# ResearchForge

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/)

ResearchForge is an autonomous multi-agent research platform. Given a question, it plans sub-queries, searches the web, crawls source pages, extracts claims, critiques the evidence, debates opposing views, and produces a structured report with a confidence score.

## Screenshot Placeholders

Add your screenshots later at the paths below.

### Dashboard
![Dashboard screenshot placeholder](docs/images/dashboard.png)

### Architecture
![Architecture screenshot placeholder](docs/images/architecture.png)

### Pipeline
![Pipeline screenshot placeholder](docs/images/pipeline.png)

### Report Output
![Report output screenshot placeholder](docs/images/report-output.png)

### Report PDF
![Report PDF screenshot placeholder](docs/images/report-pdf.png)

## What It Does

ResearchForge runs as an event-driven pipeline built on Redis Streams. A research job is published once, then each stage consumes and emits events independently until the report is finished.

The current report output includes:

- Executive summary
- Key findings
- Methodology
- Supporting evidence
- Counterarguments
- Final assessment
- Confidence score

## Architecture

```mermaid
flowchart TD
		UI[Streamlit Dashboard] --> API[FastAPI API]
		API --> RS[(Redis Streams)]

		RS --> P[Planner Agent]
		RS --> RW[Research Workers]
		RS --> C[Claim Extractor]
		RS --> K[Critic]
		RS --> D[Debate Agent]
		RS --> R[Report Agent]

		RW --> SX[SearXNG]
		RW --> CA[Crawl4AI]
		RW --> EMB[SentenceTransformers]

		C --> DB[(PostgreSQL + pgvector)]
		K --> DB
		D --> DB
		R --> DB
```

The FastAPI application is defined in [backend/api/main.py](backend/api/main.py), and the Streamlit dashboard is in [frontend/app.py](frontend/app.py).

## Pipeline

1. The user enters a research question in the Streamlit dashboard.
2. The dashboard calls the FastAPI `POST /research` endpoint.
3. The API publishes a job to the `research.jobs` Redis stream.
4. The planner creates exactly three focused sub-queries.
5. Research workers search SearXNG, crawl the selected pages with Crawl4AI, and rank results with SentenceTransformers embeddings.
6. The claim extractor turns the collected evidence into structured claims.
7. The critic challenges each claim and records weaknesses and confidence.
8. The debate agent generates skeptical and optimistic arguments.
9. The report agent synthesises the final Markdown report.
10. The API renders the Markdown into PDF with WeasyPrint.

## Tech Stack

- Backend: FastAPI, LangChain, LangGraph
- Messaging: Redis Streams via `redis-py`
- Database: PostgreSQL with pgvector
- Search: Self-hosted SearXNG
- Crawling: Crawl4AI
- Embeddings: SentenceTransformers (`BAAI/bge-small-en-v1.5`)
- Frontend: Streamlit
- PDF generation: Markdown + WeasyPrint
- Package management: uv

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- A configured LLM backend in [backend/core/llm.py](backend/core/llm.py)
- Playwright browser binaries if your environment does not already provide them

## Installation

### 1. Start infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL with pgvector, Redis, and SearXNG.

### 2. Install dependencies with uv

```bash
uv sync
```

If Crawl4AI needs browser binaries in your environment, install them with:

```bash
uv run playwright install --with-deps
```

### 3. Configure environment variables

Create a `.env` file in the project root. At minimum, set the service URLs used by the app:

```env
DATABASE_URL=postgresql+asyncpg://forge:forgepass@localhost:5432/researchforge
REDIS_URL=redis://localhost:6379
SEARXNG_BASE_URL=http://localhost:8888
```

Adjust the LLM wiring in [backend/core/llm.py](backend/core/llm.py) to match the provider and model you want to use.

### 4. Initialise the database

```bash
uv run python init_db.py
```

## Running The App

### Start the workers

```bash
uv run python services_launcher.py
```

This launches the planner, research, claim, critic, debate, and report workers.

### Start the API

```bash
uv run uvicorn backend.api.main:app --reload --port 8000
```

### Start the dashboard

```bash
uv run streamlit run frontend/app.py
```

Open http://localhost:8501 in your browser.

## Command-Line Run

You can also submit a research question from the terminal:

```bash
uv run python publish_tasks.py "Your research question here"
```

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/` | Basic health check |
| POST | `/research` | Create a new research job |
| GET | `/job/{job_id}/status` | Check job status |
| GET | `/job/{job_id}/report` | Get the structured report as JSON |
| GET | `/job/{job_id}/report/markdown` | Get the cleaned Markdown report |
| GET | `/job/{job_id}/report/pdf` | Download the rendered PDF report |
| GET | `/job/{job_id}/logs` | Fetch live agent logs for a job |

## Project Layout

```text
backend/
	api/              FastAPI application and routes
	agents/           Planner, research, claim, critic, debate, report, and gap agents
	core/             Configuration, database, Redis, and LLM setup
	models/           SQLAlchemy models for jobs, claims, critiques, reports, and related data
	services/         Search service wrappers
frontend/
	app.py            Streamlit dashboard
init_db.py          Database bootstrap script
publish_tasks.py    CLI helper for submitting a query from the terminal
services_launcher.py  Worker launcher for all core agents
docker-compose.yml  PostgreSQL, Redis, and SearXNG services
```

## Notes

- Research workers use the SearXNG instance configured by `SEARXNG_BASE_URL`.
- PDF export is generated from the Markdown report and includes the confidence score.
- The dashboard shows live agent logs while the job is running, then renders the final report and PDF download.
- Screenshot assets are not included yet; the placeholders above point to the intended file locations.
