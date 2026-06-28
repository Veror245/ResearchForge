import re
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

import markdown
from weasyprint import HTML
from backend.core.database import async_session
from backend.models import report
from backend.models.research_job import ResearchJob
from backend.models.report import ResearchReport
from sqlalchemy import select

from backend.core.redis_client import STREAM_JOBS, STREAM_LOGS, STREAM_LOGS, get_redis, publish_message


root = Path(__file__).parent.parent.parent

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
async def start_research(query: str):
    job_id = uuid4()
    rd = await get_redis()
    await publish_message(rd, STREAM_JOBS, {
        "job_id": str(job_id),
        "query": query
    })
    return {"job_id": job_id, "message": "Research job created"}



@app.get("/job/{job_id}/status")
async def get_job_status(job_id: str):
    async with async_session() as session:
        job = await session.get(ResearchJob, job_id)
        if not job:
            return {"error": "Job not found"}
        return {"job_id": job_id, "status": job.status}
    
    

@app.get("/job/{job_id}/report")
async def get_report(job_id: str):
    async with async_session() as session:
        stmt = select(ResearchReport).where(ResearchReport.job_id == job_id)
        result = await session.execute(stmt)
        report = result.scalars().first()
        if not report:
            return {"error": "Report not ready"}
        return {
            "job_id": job_id,
            "executive_summary": report.executive_summary,
            "key_findings": report.key_findings,
            "methodology": report.methodology,
            "supporting_evidence": report.supporting_evidence,
            "final_assessment": report.final_assessment,
            "confidence_score": report.confidence_score,
        }

@app.get("/job/{job_id}/report/markdown")
async def get_report_markdown(job_id: str):
    async with async_session() as session:
        stmt = select(ResearchReport).where(ResearchReport.job_id == job_id)
        result = await session.execute(stmt)
        report = result.scalars().first()
        if not report:
            raise HTTPException(status_code=404, detail="Report not ready")
        # Use the existing clean_markdown_for_pdf() function you already have
        cleaned = clean_markdown_for_pdf(report.to_markdown())
        return {"job_id": job_id, "markdown": cleaned}
    
from fastapi.responses import FileResponse
import tempfile

@app.get("/job/{job_id}/report/pdf")
async def get_report_pdf(job_id: str):
    async with async_session() as session:
        stmt = select(ResearchReport).where(ResearchReport.job_id == job_id)
        result = await session.execute(stmt)
        report = result.scalars().first()
        if not report:
            raise HTTPException(status_code=404, detail="Report not ready")
        cleaned = clean_markdown_for_pdf(report.to_markdown())
        cleaned = cleaned.strip()
        extensions = ["tables", "fenced_code", "codehilite", "nl2br"]
        try:
            html_body = markdown.markdown(cleaned, extensions=extensions, output_format='html')
        except Exception as e:
            print(f"  Markdown conversion error: {e}")
            html_body = f"<pre>{cleaned}</pre>"

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
        # Save to a temp file and return it
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            HTML(string=html_full).write_pdf(tmp.name)
            return FileResponse(tmp.name, media_type="application/pdf", filename=f"report_{job_id}.pdf")
        
@app.get("/job/{job_id}/logs")
async def get_job_logs(job_id: str, count: int = 50):
    rd = await get_redis()
    # Read latest messages; you could filter more precisely with xrange
    messages = await rd.xrevrange(STREAM_LOGS, max="+", min="-", count=count)
    logs = []
    for msg_id, fields in messages: # type: ignore
        if fields.get("job_id") == job_id: # type: ignore
            logs.append({
                "agent": fields.get("agent"), # type: ignore
                "message": fields.get("message"), # type: ignore
                "ts": fields.get("ts") # type: ignore
            })
    # Reverse to show oldest first
    logs.reverse()
    return {"job_id": job_id, "logs": logs}