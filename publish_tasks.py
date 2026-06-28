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
    """Fix common LLM markdown mistakes and enforce professional report formatting."""
    if not raw_md:
        return ""
    
    text = raw_md.replace('\r\n', '\n')
    
    # 1. Convert fancy bullets to standard markdown
    text = re.sub(r'^[\s]*[•◦▪▹▸]\s*', '- ', text, flags=re.MULTILINE)
    
    # 2. Split inline numbered lists: "1. foo 2. bar" -> proper list
    def split_inline_lists(content: str) -> str:
        lines = content.split('\n')
        result = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Detect "1. text 2. text" patterns
            if re.search(r'\d+\.\s.+?\s+\d+\.\s', line):
                parts = re.split(r'\s+(?=\d+\.\s)', line)
                result.extend(parts)
            # Detect "- text - text" patterns  
            elif re.search(r'[-*]\s.+?\s+[-*]\s', line):
                parts = re.split(r'\s+(?=[-*]\s)', line)
                result.extend(parts)
            else:
                result.append(line)
        return '\n'.join(result)
    
    text = split_inline_lists(text)
    
    # 3. Remove orphaned/empty list markers
    text = re.sub(r'^[ \t]*\d+\.[ \t]*(?:\n|$)', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[ \t]*[-*][ \t]*(?:\n|$)', '', text, flags=re.MULTILINE)
    
    # 4. Ensure headings have proper spacing
    text = re.sub(r'([^\n])\n(#{1,6}\s)', r'\1\n\n\2', text)
    text = re.sub(r'(#{1,6}\s[^\n]+)\n([^\n#])', r'\1\n\n\2', text)
    
    # 5. Process paragraph blocks
    paragraphs = re.split(r'\n\s*\n', text)
    cleaned = []
    
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        
        lines = p.split('\n')
        list_markers = [i for i, line in enumerate(lines) 
                       if re.match(r'^\s*(\d+\.\s|[-*]\s)', line.strip())]
        
        if len(list_markers) >= 2:
            # Multi-item list block: keep each item on its own line,
            # but join wrapped lines to their parent item
            items = []
            current = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if re.match(r'^\s*(\d+\.\s|[-*]\s)', line):
                    if current:
                        items.append(' '.join(current))
                    current = [line]
                else:
                    current.append(line)
            if current:
                items.append(' '.join(current))
            cleaned.append('\n'.join(items))
            
        elif len(list_markers) == 1 and len(lines) > 1:
            # Single list item with wrapped text — join it
            cleaned.append(' '.join(lines))
        else:
            # Regular paragraph — unwrap hard line breaks
            p = re.sub(r'\n', ' ', p)
            p = re.sub(r' +', ' ', p)
            cleaned.append(p)
    
    result = '\n\n'.join(cleaned)
    
    # 6. Bold standalone section headers (e.g., "Key Findings:")
    result = re.sub(
        r'^([A-Z][A-Za-z\s.\-/&()]{2,50}:)$',
        r'**\1**',
        result,
        flags=re.MULTILINE
    )
    
    # 7. Ensure lists are separated from paragraphs
    result = re.sub(r'([^\n])\n(\d+\.\s)', r'\1\n\n\2', result)
    result = re.sub(r'([^\n])\n(-\s)', r'\1\n\n\2', result)
    
    # 8. Clean up excessive whitespace
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()

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

                raw_md = report.to_markdown() if hasattr(report, 'to_markdown') else ""
                raw_md = clean_markdown_for_pdf(raw_md)
                raw_md = raw_md.strip()

                extensions = ["tables", "fenced_code", "codehilite", "nl2br"]
                try:
                    html_body = markdown.markdown(raw_md, extensions=extensions, output_format='html')
                except Exception as e:
                    print(f"  Markdown conversion error: {e}")
                    html_body = f"<pre>{raw_md}</pre>"

                confidence = (
                    f"{report.confidence_score:.0%}"
                    if report.confidence_score is not None
                    else "N/A"
                )

                html_full = f"""<!DOCTYPE html>
            <html lang="en">
            <head>
            <meta charset="utf-8">
            <style>
                @page {{
                    size: A4;
                    margin: 2.5cm 2cm;
                }}
                body {{
                    font-family: Georgia, "Times New Roman", serif;
                    font-size: 11pt;
                    line-height: 1.65;
                    color: #1f2937;
                    margin: 0;
                    padding: 0;
                }}
                h1 {{
                    font-family: Arial, Helvetica, sans-serif;
                    font-size: 22pt;
                    font-weight: 700;
                    text-align: center;
                    color: #111827;
                    margin: 0 0 35px 0;
                    padding-bottom: 18px;
                    border-bottom: 3px solid #111827;
                    letter-spacing: -0.3px;
                }}
                h2 {{
                    font-family: Arial, Helvetica, sans-serif;
                    font-size: 14pt;
                    font-weight: 600;
                    color: #374151;
                    border-bottom: 2px solid #e5e7eb;
                    padding-bottom: 8px;
                    margin-top: 32px;
                    margin-bottom: 16px;
                    page-break-after: avoid;
                }}
                h3 {{
                    font-family: Arial, Helvetica, sans-serif;
                    font-size: 12pt;
                    font-weight: 600;
                    color: #4b5563;
                    margin-top: 22px;
                    margin-bottom: 10px;
                    page-break-after: avoid;
                }}
                p {{
                    margin: 0 0 12px 0;
                    text-align: justify;
                    orphans: 3;
                    widows: 3;
                }}
                ul, ol {{
                    margin: 14px 0;
                    padding-left: 28px;
                }}
                li {{
                    margin: 8px 0;
                    padding-left: 6px;
                    text-align: left;
                }}
                li > p {{
                    margin: 0;
                }}
                ol li {{
                    padding-left: 10px;
                }}
                strong {{
                    color: #111827;
                    font-weight: 600;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 20px 0;
                    font-size: 10pt;
                    page-break-inside: avoid;
                }}
                table, th, td {{
                    border: 1px solid #d1d5db;
                }}
                th, td {{
                    padding: 10px 12px;
                    text-align: left;
                    vertical-align: top;
                }}
                th {{
                    background-color: #f9fafb;
                    font-family: Arial, Helvetica, sans-serif;
                    font-weight: 600;
                    color: #374151;
                }}
                tr:nth-child(even) {{
                    background-color: #fafafa;
                }}
                pre {{
                    background: #f3f4f6;
                    padding: 14px;
                    overflow-x: auto;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                    border-left: 4px solid #d1d5db;
                    font-size: 10pt;
                    margin: 16px 0;
                }}
                code {{
                    font-family: "Courier New", Courier, monospace;
                    background: #f3f4f6;
                    padding: 2px 5px;
                    border-radius: 3px;
                    font-size: 9.5pt;
                }}
                blockquote {{
                    border-left: 4px solid #9ca3af;
                    padding-left: 18px;
                    color: #4b5563;
                    margin: 20px 0;
                    font-style: italic;
                }}
                hr {{
                    border: none;
                    border-top: 1px solid #e5e7eb;
                    margin: 30px 0;
                }}
                .confidence-box {{
                    text-align: center;
                    margin-top: 30px;
                    padding: 18px;
                    border: 2px solid #e5e7eb;
                    background: #f9fafb;
                }}
                .confidence-label {{
                    font-family: Arial, Helvetica, sans-serif;
                    font-size: 10pt;
                    color: #6b7280;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    margin-bottom: 6px;
                }}
                .confidence-value {{
                    font-family: Arial, Helvetica, sans-serif;
                    font-size: 20pt;
                    font-weight: 700;
                    color: #111827;
                }}
            </style>
            </head>
            <body>
            {html_body}
            <div class="confidence-box">
                <div class="confidence-label">Confidence Score</div>
                <div class="confidence-value">{confidence}</div>
            </div>
            </body>
            </html>"""
                try:
                    safe_name = re.sub(r'[^\w\-]', '_', job.query)[:50]
                    HTML(string=html_full).write_pdf(f"data/report_{safe_name}.pdf")
                    print(f"  PDF saved as report_{safe_name}.pdf")
                    return raw_md, html_full
                except Exception as e:
                    print(f"  PDF generation failed: {e}")
            else:
                print("  No report found.")

# if __name__ == "__main__":
#     if len(sys.argv) > 1:
#         queries = sys.argv[1:]
#     else:
#         queries = ["What Are the latest advancements in AI for medical diagnostics?"]
#     asyncio.run(main(queries=queries))