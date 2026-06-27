import asyncio
import re
import sys
import time
from uuid import uuid4, UUID

from sqlalchemy import select
from weasyprint import HTML
import markdown

from backend.core.redis_client import (
    STREAM_JOBS,
    get_redis,
    STREAM_TASKS,
    STREAM_TASK_EVENTS,      # new event stream
    publish_message,
)
from backend.core.database import async_session
from backend.models.research_job import ResearchJob
from backend.models.research_task import ResearchTask
from backend.models.claim_db import Claim
from backend.models.report import ResearchReport
from backend.models.critic import Critique
from backend.models.debate import Skeptic, Optimist
import backend.models  # ensure all models are loaded

# ---------------------------------------------------------------------------
# 1. Event‑driven waiter – replaces all wait_for_* functions
# ---------------------------------------------------------------------------
async def wait_for_job_event(job_id: UUID, event_type: str, timeout: float = 600) -> bool:
    """Block until an event for the given job appears on the event stream."""
    rd = await get_redis()
    group = f"test-wait-{uuid4()}"
    try:
        await rd.xgroup_create(STREAM_TASK_EVENTS, group, id="$", mkstream=True)
    except Exception:
        pass

    start = time.time()
    while time.time() - start < timeout:
        try:
            msgs = await rd.xreadgroup(
                groupname=group,
                consumername="test",
                streams={STREAM_TASK_EVENTS: ">"},
                count=10,
                block=5000,
            )
        except Exception:
            await asyncio.sleep(1)
            continue

        for _, msg_list in msgs:
            for msg_id, fields in msg_list: # type: ignore
                if fields.get("job_id") == str(job_id) and fields.get("event") == event_type:
                    await rd.xack(STREAM_TASK_EVENTS, group, msg_id)
                    return True
                await rd.xack(STREAM_TASK_EVENTS, group, msg_id)
        await asyncio.sleep(0.5)
    return False

# ---------------------------------------------------------------------------
# 2. PDF helper (unchanged)
# ---------------------------------------------------------------------------
def clean_markdown_for_pdf(raw_md: str) -> str:
    """Fix common LLM markdown mistakes so the PDF conversion works properly."""
    raw_md = re.sub(r'^[\s]*[•◦▪▹▸]\s*', '- ', raw_md, flags=re.MULTILINE)
    raw_md = re.sub(r'^[ \t]*\d+\.[ \t]*\n', '', raw_md, flags=re.MULTILINE)
    raw_md = re.sub(r'^[ \t]*\d+\.[ \t]*$', '', raw_md, flags=re.MULTILINE)
    raw_md = re.sub(r'(?<!\n)\n(?=[A-Z][\w\s.\-/&()]{2,50}:\s)', '\n\n', raw_md)

    paragraphs = re.split(r'\n\s*\n', raw_md)
    cleaned = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if re.match(r'^\s*(\d+\.\s|[-*]\s)', p):
            lines = p.split('\n')
            first_line = lines[0]
            rest = ' '.join(line.strip() for line in lines[1:])
            cleaned.append(first_line + (' ' + rest if rest else ''))
        else:
            p = re.sub(r'\n', ' ', p)
            p = re.sub(r' +', ' ', p)
            cleaned.append(p)
    result = '\n\n'.join(cleaned)

    result = re.sub(r'^([A-Z][\w\s.\-/&()]{2,50}:)', r'**\1**', result, flags=re.MULTILINE)
    result = re.sub(r'([^\n])\n(\d+\.\s|[-*]\s)', r'\1\n\n\2', result)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result

# ---------------------------------------------------------------------------
# 3. Main – event‑driven test
# ---------------------------------------------------------------------------
async def main(queries: list[str]):
    rd = await get_redis()

    for query in queries:
        # 3.1 Create a job ID upfront and publish it together with the query
        job_id = uuid4()
        await publish_message(rd, STREAM_JOBS, {
            "job_id": str(job_id),
            "query": query
        })
        print(f"Published job: {job_id} – {query}")

        # 3.2 Wait for the final report event for this job
        print(f"Waiting for report on job {job_id} ...")
        ok = await wait_for_job_event(job_id, "report_completed", timeout=600)
        if not ok:
            print(f"ERROR: Timeout waiting for report on job {job_id}")
            continue

        # 3.3 All done – fetch everything by job_id and print
        async with async_session() as session:
            job = await session.get(ResearchJob, job_id)
            if not job:
                print(f"Job {job_id} not found in DB.")
                continue

            print(f"\n{'='*60}")
            print(f"Research Job: {job.query}")
            print(f"Status: {job.status}")

            # ---- Claims (now stored with job_id) ----
            stmt = select(Claim).where(Claim.job_id == job_id)
            claims = (await session.execute(stmt)).scalars().all()
            print(f"\nClaims extracted: {len(claims)}")
            for i, claim in enumerate(claims, 1):
                print(f"  Claim {i}:")
                print(f"    Text: {claim.text}")
                print(f"    Evidence: {(claim.evidence or '')[:200]}...")
                print(f"    Confidence: {claim.confidence:.2f}")
                print(f"    Importance: {claim.importance}")
                print(f"    Type: {claim.type}")
                print("    ---")

            # ---- Critiques (stored with job_id) ----
            crit_stmt = select(Critique).where(Critique.job_id == job_id)
            critiques = (await session.execute(crit_stmt)).scalars().all()
            print(f"\nCritiques generated: {len(critiques)}")
            for i, critique in enumerate(critiques, 1):
                print(f"  Critique {i}:")
                print(f"    Critic: {critique.critic_name}")
                print(f"    Text: {critique.critique_text[:200]}...")
                print(f"    Score: {critique.score:.2f}")
                print(f"    Severity: {critique.severity}")
                print(f"    Evidence: {(critique.evidence or 'N/A')[:200]}...")
                print("    ---")

            skeptic_stmt = select(Skeptic).where(Skeptic.job_id == job_id)
            skeptics = (await session.execute(skeptic_stmt)).scalars().all()
            print(f"\nSkeptical arguments generated: {len(skeptics)}")
            for i, skeptic in enumerate(skeptics, 1):
                print(f"  Skeptic {i}:")
                print(f"    Arguments: {skeptic.arguments[:200]}...")
                print("    ---")
            
            optimist_stmt = select(Optimist).where(Optimist.job_id == job_id)
            optimists = (await session.execute(optimist_stmt)).scalars().all()
            print(f"\nOptimistic arguments generated: {len(optimists)}")
            for i, optimist in enumerate(optimists, 1):
                print(f"  Optimist {i}:")
                print(f"    Arguments: {optimist.arguments[:200]}...")
                print("    ---")
            # ---- Report ----
            report_stmt = select(ResearchReport).where(ResearchReport.job_id == job_id)
            report = (await session.execute(report_stmt)).scalars().first()
            if report:
                print(f"\nReport generated: {report.id}")
                print(f"Executive Summary: {report.executive_summary[:200]}...")

                # Generate PDF
                raw_md = report.to_markdown() if hasattr(report, 'to_markdown') else ""
                raw_md = clean_markdown_for_pdf(raw_md)
                raw_md = re.sub(r'\n{3,}', '\n\n', raw_md)
                raw_md = re.sub(r'([^\n])\n(#{1,6} )', r'\1\n\n\2', raw_md)
                raw_md = raw_md.strip()

                extensions = ["tables", "fenced_code", "codehilite", "nl2br"]
                try:
                    html_body = markdown.markdown(raw_md, extensions=extensions, output_format='html')
                except Exception as e:
                    print(f"  Markdown conversion error: {e}")
                    html_body = f"<pre>{raw_md}</pre>"

                html_full = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
    body {{ font-family: Arial, sans-serif; margin: 50px; line-height: 1.7; color: #222; }}
    h1 {{ text-align: center; color: #1f2937; margin-bottom: 40px; }}
    h2 {{ color: #374151; border-bottom: 2px solid #e5e7eb; padding-bottom: 6px; margin-top: 30px; }}
    h3 {{ color: #4b5563; margin-top: 20px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
    table, th, td {{ border: 1px solid #ddd; }}
    th, td {{ padding: 8px; text-align: left; }}
    th {{ background-color: #f9fafb; }}
    pre {{ background: #f5f5f5; padding: 12px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; }}
    code {{ font-family: monospace; }}
    blockquote {{ border-left: 4px solid #ccc; padding-left: 12px; color: #555; margin: 20px 0; }}
    ul, ol {{ margin: 10px 0; padding-left: 30px; }}
    li {{ margin: 6px 0; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
                try:
                    safe_name = job.query.replace(' ', '_').replace('/', '_')[:50]
                    HTML(string=html_full).write_pdf(f"data/report_{safe_name}.pdf")
                    print(f"  PDF saved as report_{safe_name}.pdf")
                except Exception as e:
                    print(f"  PDF generation failed: {e}")
            else:
                print("  No report found.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        queries = sys.argv[1:]
    else:
        queries = ["What Are the latest advancements in AI for medical diagnostics?"]
    asyncio.run(main(queries=queries))