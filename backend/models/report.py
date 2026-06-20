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


class ReportSchema(BaseModel):
    executive_summary: str = Field(
        description="A Detailed Research Report for the Given Findings and Claims"
    )
    key_findings: Optional[str] = Field(
        description="Key findings from the research."
    )
    methodology: Optional[str] = Field(
        description="The methodology used in the research."
    )
    supporting_evidence: Optional[str] = Field(
        description="Supporting evidence for the research findings."
    )
    # counterarguments: Optional[str] = Field(
    #     description="Counterarguments to the research findings."
    # )
    final_assessment: Optional[str] = Field(
        description="The final assessment of the research findings."
    )
    confidence_score: Optional[float] = Field(
        description="The confidence score for the research findings."
    )