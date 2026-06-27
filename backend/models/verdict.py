from uuid import UUID
from sqlalchemy import Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin, generate_uuid

class Verdict(Base, TimestampMixin):
    __tablename__ = "verdicts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=generate_uuid)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["ResearchJob"] = relationship(back_populates="verdicts")  # type: ignore
    
    
from pydantic import BaseModel, Field

class VerdictSchema(BaseModel):
    conclusion: str = Field(description="Final conclusion of the research")
    confidence: float = Field(ge=0, le=1, description="Confidence score (0-1)")
    reasoning: str | None = Field(None, description="Detailed reasoning behind the verdict")