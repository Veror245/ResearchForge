import re
from textwrap import dedent
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field
from sqlalchemy import Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin, generate_uuid

class ResearchReport(Base, TimestampMixin):
    __tablename__ = "research_reports"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=generate_uuid)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False
    )
    # You could also link to a job if you prefer job-level reports
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_jobs.id"), nullable=True)

    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_findings: Mapped[str] = mapped_column(Text, nullable=True)
    methodology: Mapped[str] = mapped_column(Text, nullable=True)
    supporting_evidence: Mapped[str] = mapped_column(Text, nullable=True)
    counterarguments: Mapped[str] = mapped_column(Text, nullable=True)
    final_assessment: Mapped[str] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)

    task: Mapped["ResearchTask"] = relationship(back_populates="reports") # type: ignore
    job: Mapped["ResearchJob"] = relationship(back_populates="reports") # type: ignore

    
    def _sanitize_field(self, value: str | None) -> str:
        if not value:
            return "N/A"

        value = value.strip()

        # Remove stray H1 titles
        value = re.sub(r'^#\s+.*?\n+', '', value, count=1)

        # Remove stray numbered list markers on their own lines (LLM artifact)
        # e.g. "1.\n2.\n3.\n" inserted mid-sentence by the model
        value = re.sub(r'^[ \t]*\d+\.[ \t]*\n', '', value, flags=re.MULTILINE)
        value = re.sub(r'^[ \t]*\d+\.[ \t]*$', '', value, flags=re.MULTILINE)

        # Remove trailing JSON brackets / code fences
        value = re.sub(r'\s*[\[\}]\s*$', '', value)
        value = re.sub(r'^```[a-z]*\n', '', value)
        value = re.sub(r'\n```$', '', value)

        # Close unclosed code fences
        open_fences = len(re.findall(r'^```', value, re.MULTILINE))
        if open_fences % 2 != 0:
            value += "\n```"

        # Remove excessive blank lines (keep at most one consecutive blank line)
        value = re.sub(r'\n{3,}', '\n\n', value)

        return value.strip()
    
    def to_markdown(self) -> str:
        confidence = (
            f"{self.confidence_score:.0%}"
            if self.confidence_score is not None
            else "N/A"
        )
        return dedent(f"""
        # Research Report

        ## Executive Summary

        {self._sanitize_field(self.executive_summary)}

        ## Key Findings

        {self._sanitize_field(self.key_findings)}

        ## Methodology

        {self._sanitize_field(self.methodology)}

        ## Supporting Evidence

        {self._sanitize_field(self.supporting_evidence)}

        ## Counterarguments

        {self._sanitize_field(self.counterarguments)}

        ## Final Assessment

        {self._sanitize_field(self.final_assessment)}

        ## Confidence Score

        **{confidence}**
        """).strip()

class ReportSchema(BaseModel):
    executive_summary: str = Field(
        description="A Detailed Research Report for the Given Findings and Claims. Do not include markdown headings."
    )
    key_findings: Optional[str] = Field(
        description="Key findings from the research in. Do not include markdown headings."
    )
    methodology: Optional[str] = Field(
        description="The methodology used in the research in. Do not include markdown headings."
    )
    supporting_evidence: Optional[str] = Field(
        description="Supporting evidence for the research findings in. Do not include markdown headings."
    )
    # counterarguments: Optional[str] = Field(
    #     description="Counterarguments to the research findings."
    # )
    final_assessment: Optional[str] = Field(
        description="The final assessment of the research findings in. Do not include markdown headings."
    )
    
    