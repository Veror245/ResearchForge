from enum import Enum as PyEnum
from uuid import UUID
from sqlalchemy import String, Text, Float, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from .base import Base, TimestampMixin, generate_uuid

# Re-use the same enum values as the Pydantic model to keep them in sync
class ClaimType(str, PyEnum):
    FACT = "fact"
    DECISION = "decision"
    METRIC = "metric"
    RELATIONSHIP = "relationship"
    REQUIREMENT = "requirement"
    LIMITATION = "limitation"

class Claim(Base, TimestampMixin):
    __tablename__ = "claims"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=generate_uuid)

    # Foreign keys – both nullable to support task‑level and finding‑level claims
    task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=True
    )
    finding_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_findings.id", ondelete="CASCADE"), nullable=True
    )

    # Core claim fields matching the Pydantic schema
    text: Mapped[str] = mapped_column(Text, nullable=False)          # the claim itself
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True) # supporting snippet
    confidence: Mapped[float] = mapped_column(Float, default=0.5)    # 0.0–1.0
    importance: Mapped[float] = mapped_column(Float, default=5.0)    # 0–10
    type: Mapped[str] = mapped_column(
    String(20), nullable=False, default=ClaimType.FACT.value
    )
    # Vector embedding for semantic search (1536 dims for OpenAI ada-002, adjust if needed)
    embedding = mapped_column(Vector(1536), nullable=True)
    chunk = mapped_column(Text, nullable=True)  # optional chunk of text from which the claim was extracted


    # Relationships (optional, for ORM convenience)
    task: Mapped["ResearchTask"] = relationship("ResearchTask", back_populates="claims") # type: ignore
    finding: Mapped["ResearchFinding"] = relationship("ResearchFinding", back_populates="claims") # type: ignore
    critiques: Mapped[list["Critique"]] = relationship("Critique", back_populates="claim", cascade="all, delete-orphan") # type: ignore