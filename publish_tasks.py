import asyncio
from uuid import uuid4, UUID
from sqlalchemy import select
from langchain_core.prompts import ChatPromptTemplate
from backend.core.redis_client import get_redis, STREAM_TASKS, publish_message
from backend.core.database import async_session
from backend.models.research_task import ResearchTask
from backend.models.claim_db import Claim
from backend.models.report import ResearchReport
from backend.core.llm import llm
import markdown
from weasyprint import HTML
import re
import sys
import backend.models

async def wait_for_tasks(task_ids: list[UUID], timeout: float = 300):
    elapsed = 0
    while elapsed < timeout:
        async with async_session() as session:
            stmt = select(ResearchTask.status).where(ResearchTask.id.in_(task_ids))
            result = await session.execute(stmt)
            statuses = [row[0] for row in result]
            if all(s in ("completed", "failed") for s in statuses):
                return
        await asyncio.sleep(1)
        elapsed += 1

async def wait_for_claims(task_id: UUID, timeout: float = 300):
    """Wait until at least one claim exists for the given task."""
    elapsed = 0
    while elapsed < timeout:
        async with async_session() as session:
            stmt = select(Claim).where(Claim.task_id == task_id)
            result = await session.execute(stmt)
            if result.scalars().first():
                return True
        await asyncio.sleep(1)
        elapsed += 1
    return False

async def wait_for_report(task_id: UUID, timeout: float = 300):
    """Wait until a report is generated for the given task."""
    elapsed = 0
    while elapsed < timeout:
        async with async_session() as session:
            stmt = select(ResearchReport).where(ResearchReport.task_id == task_id)
            result = await session.execute(stmt)
            if result.scalars().first():
                return True
        await asyncio.sleep(1)
        elapsed += 1
    return False

def clean_markdown_for_pdf(raw_md: str) -> str:
    """Fix common LLM markdown mistakes so the PDF conversion works properly."""

    # 1. Replace forbidden bullet characters with proper markdown bullets
    raw_md = re.sub(r'^[\s]*[•◦▪▹▸]\s*', '- ', raw_md, flags=re.MULTILINE)

    # 2. Remove stray numbered list markers on their own lines (LLM artifact)
    #    These lines contain ONLY a number+period with no actual content.
    #    We include the trailing newline so surrounding text rejoins seamlessly.
    raw_md = re.sub(r'^[ \t]*\d+\.[ \t]*\n', '', raw_md, flags=re.MULTILINE)
    raw_md = re.sub(r'^[ \t]*\d+\.[ \t]*$', '', raw_md, flags=re.MULTILINE)

    # 3. Split labeled items into their own paragraphs.
    #    Detect a "Label Name:" pattern (title-case phrase, 3-51 chars) at the
    #    start of a line and insert a blank line before it if missing.
    #    The (?<!\n) lookbehind prevents double-blanking.
    raw_md = re.sub(
        r'(?<!\n)\n(?=[A-Z][\w\s.\-/&()]{2,50}:\s)',
        '\n\n',
        raw_md,
    )

    # 4. Reflow paragraphs: collapse single newlines into spaces,
    #    but preserve double newlines (paragraph separators).
    paragraphs = re.split(r'\n\s*\n', raw_md)
    cleaned = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        # List items: preserve the marker, reflow the wrapped content
        if re.match(r'^\s*(\d+\.\s|[-*]\s)', p):
            lines = p.split('\n')
            first_line = lines[0]
            rest = ' '.join(line.strip() for line in lines[1:])
            cleaned.append(first_line + (' ' + rest if rest else ''))
        else:
            # Regular paragraph: merge hard-wrapped lines into one
            p = re.sub(r'\n', ' ', p)
            p = re.sub(r' +', ' ', p)
            cleaned.append(p)

    result = '\n\n'.join(cleaned)

    # 5. Bold labeled items for better readability in the PDF
    #    "Resource Inefficiency:" → "**Resource Inefficiency:**"
    result = re.sub(
        r'^([A-Z][\w\s.\-/&()]{2,50}:)',
        r'**\1**',
        result,
        flags=re.MULTILINE,
    )

    # 6. Ensure blank lines before lists if missing
    result = re.sub(r'([^\n])\n(\d+\.\s|[-*]\s)', r'\1\n\n\2', result)

    # 7. Remove excessive blank lines (more than one)
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result

async def main(queries: list[str]):
    rd = await get_redis()
    # queries = [
    #     "What are the most horrifying skin crawling horror movies of all time?",
    # ]

    task_ids = []
    async with async_session() as session:
        for query in queries:
            task = ResearchTask(id=uuid4(), query=query, status="pending")
            session.add(task)
            await session.flush()
            await session.commit()
            task_id_str = str(task.id)
            task_ids.append(task.id)
            await publish_message(rd, STREAM_TASKS, {"task_id": task_id_str, "query": query})
            print(f"Published task: {task_id_str} - {query}")
        await session.commit()

    print("\nWaiting for research to complete...")
    await wait_for_tasks(task_ids, timeout=300)

    print("Research completed. Waiting for claim extraction to finish...")
    for tid in task_ids:
        found = await wait_for_claims(tid, timeout=300)
        if not found:
            print(f"Warning: no claims found for task {tid} after timeout.")

    # Now fetch and print claims
    async with async_session() as session:
        for tid in task_ids:
            task = await session.get(ResearchTask, tid)
            if not task:
                continue
            print(f"\nTask: {task.query} (status: {task.status})")
            stmt = select(Claim).where(Claim.task_id == tid)
            result = await session.execute(stmt)
            claims = result.scalars().all()
            if not claims:
                print("  No claims extracted.")
                continue
            for i, claim in enumerate(claims, 1):
                print(f"  Claim {i}:")
                print(f"    Text: {claim.text}")
                print(f"    Evidence: {(claim.evidence or '')[:200]}...")
                print(f"    Confidence: {claim.confidence:.2f}")
                print(f"    Importance: {claim.importance}")
                print(f"    Type: {claim.type}")
                print("    ---")
    
    print("Waiting for report generation to complete...")
    for tid in task_ids:
        found = await wait_for_report(tid, timeout=600)
        if not found:
            print(f"Warning: no report generated for task {tid} after timeout.")
            
    async with async_session() as session:
        for tid in task_ids:
            task = await session.get(ResearchTask, tid)
            if not task:
                continue
            print(f"\nGenerating PDF for task: {task.query} (status: {task.status})")
            stmt = select(ResearchReport).where(ResearchReport.task_id == tid)
            result = await session.execute(stmt)
            report = result.scalars().first()
            if not report:
                print("  No report found.")
                continue

            print(f"  Report ID: {report.id}")
            print(f"  Executive Summary: {report.executive_summary[:200]}...")
            
            print(report)
            print(report.to_markdown()[:500])

            # 1. Get raw markdown and clean it up
            raw_md = report.to_markdown() if hasattr(report, 'to_markdown') else ""
            raw_md = clean_markdown_for_pdf(raw_md)
            # Remove multiple consecutive blank lines, but keep two newlines for paragraphs
            raw_md = re.sub(r'\n{3,}', '\n\n', raw_md)
            # Ensure each heading has a leading newline (except start)
            raw_md = re.sub(r'([^\n])\n(#{1,6} )', r'\1\n\n\2', raw_md)
            # Trim excessive whitespace
            raw_md = raw_md.strip()

            # 2. Convert to HTML with essential extensions
            extensions = ["tables", "fenced_code", "codehilite", "nl2br"]
            try:
                html_body = markdown.markdown(raw_md, extensions=extensions, output_format='html')
            except Exception as e:
                print(f"  Markdown conversion error: {e}")
                # Fallback: render as plain text with <pre>
                html_body = f"<pre>{raw_md}</pre>"

            # 3. Full HTML template
            html_full = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 50px;
            line-height: 1.7;
            color: #222;
        }}
        h1 {{
            text-align: center;
            color: #1f2937;
            margin-bottom: 40px;
        }}
        h2 {{
            color: #374151;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 6px;
            margin-top: 30px;
        }}
        h3 {{
            color: #4b5563;
            margin-top: 20px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
        }}
        table, th, td {{
            border: 1px solid #ddd;
        }}
        th, td {{
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #f9fafb;
        }}
        pre {{
            background: #f5f5f5;
            padding: 12px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        code {{
            font-family: monospace;
        }}
        blockquote {{
            border-left: 4px solid #ccc;
            padding-left: 12px;
            color: #555;
            margin: 20px 0;
        }}
        ul, ol {{
            margin: 10px 0;
            padding-left: 30px;
        }}
        li {{
            margin: 6px 0;
        }}
    </style>
    </head>
    <body>
    {html_body}
    </body>
    </html>"""

            # 4. Write PDF
            try:
                HTML(string=html_full).write_pdf(f"data/report_{task.query.replace(' ', '_')}.pdf")
                print(f"  PDF saved as report_{task.query.replace(' ', '_')}.pdf")
            except Exception as e:
                print(f"  PDF generation failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        queries = sys.argv[1:]
    else:
        queries = [
            "What Happens Due to O3 Deficiency in Humans ?",
        ]
    asyncio.run(main(queries=queries))

#TODO: FIX DOWNSTREAM CONSUMERS