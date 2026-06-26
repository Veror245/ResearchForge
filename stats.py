import asyncio
import re
import sys
from uuid import UUID
from markdown import markdown
from sqlalchemy import select
from weasyprint import HTML
from backend.core.database import async_session
from backend.models.report import ResearchReport
from backend.models.research_job import ResearchJob
from backend.models.research_finding import ResearchFinding
from backend.models.claim_db import Claim



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

async def main(job_id_str: str):
    job_uuid = UUID(job_id_str)
    async with async_session() as session:
        job = await session.get(ResearchJob, job_uuid)
        if not job:
            print(f"Job {job_id_str} not found.")
            return

        # 1. Findings markdown
        stmt = select(ResearchFinding).where(ResearchFinding.job_id == job_uuid)
        findings = (await session.execute(stmt)).scalars().all()
        total_findings_chars = sum(len(f.markdown_content or "") for f in findings)
        total_findings_words = sum(len((f.markdown_content or "").split()) for f in findings)

        # 2. Claims markdown (as formatted)
        claims_stmt = select(Claim).where(Claim.job_id == job_uuid)
        claims = (await session.execute(claims_stmt)).scalars().all()
        claims_md = ""
        for c in claims:
            claims_md += f"- {c.text}\n"
            if c.evidence:
                claims_md += f"  {c.evidence}\n"
            claims_md += "\n"
        total_claims_chars = len(claims_md)
        total_claims_words = len(claims_md.split())
        
        report_stmt = select(ResearchReport).where(ResearchReport.job_id == job_uuid)
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

        # Print stats
        print(f"Job: {job.query[:80]}...")
        print(f"Findings: {len(findings)} pages")
        print(f"  Total chars: {total_findings_chars:,}")
        print(f"  Total words: {total_findings_words:,}")
        print(f"Claims: {len(claims)} extracted")
        print(f"  Formatted chars: {total_claims_chars:,}")
        print(f"  Formatted words: {total_claims_words:,}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stats <job_id>")
    else:
        asyncio.run(main(sys.argv[1]))