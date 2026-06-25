import enum

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import  String, Text, Float, ForeignKey
from .base import Base, TimestampMixin, generate_uuid
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID

class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class Critique(Base, TimestampMixin):
    __tablename__ = "critiques"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=generate_uuid)
    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    
    critic_name: Mapped[str] = mapped_column(Text, nullable=False)
    critique_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[Severity] = mapped_column(String(20), nullable=False, default=Severity.LOW.value)
    chunk: Mapped[str | None] = mapped_column(Text, nullable=True)  # optional chunk of text from which the critique was derived

    claim: Mapped["Claim"] = relationship(back_populates="critiques") # type: ignore
    task: Mapped["ResearchTask"] = relationship(back_populates="critiques") # type: ignore
    job: Mapped["ResearchJob"] = relationship(back_populates="critiques") # type: ignore

class CritiqueSchema(BaseModel):
    critic_name: str = Field(
        description="Name or identifier of the critic (e.g., 'LLM Critic', 'Peer Reviewer 1')"
    )
    critique_text: str = Field(
        description="The actual critique text"
    )
    evidence: Optional[str] = Field(
        description="Optional evidence or rationale supporting the critique"
    )
    score: float = Field(
        description="The score assigned to the critique"
    )
    severity: Severity = Field(
        description="The severity level of the critique"
    )

class CritiquesResponse(BaseModel):
    critiques: list[CritiqueSchema] = Field(description="List of critiques extracted from the claim")