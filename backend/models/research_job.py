# backend/models/research_job.py
from uuid import UUID
from sqlalchemy import String, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin, generate_uuid
import enum

class JobStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class ResearchJob(Base, TimestampMixin):
    __tablename__ = "research_jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=generate_uuid)
    query: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus), default=JobStatus.PENDING, nullable=False
    )

    tasks: Mapped[list["ResearchTask"]] = relationship( # type: ignore
        "ResearchTask", back_populates="job", lazy="selectin"
    )
    
    claims: Mapped[list["Claim"]] = relationship( # type: ignore
        "Claim", back_populates="job", lazy="selectin"
    )
    
    findings: Mapped[list["ResearchFinding"]] = relationship( # type: ignore
        "ResearchFinding", back_populates="job", lazy="selectin"
    )
    
    critiques: Mapped[list["Critique"]] = relationship("Critique", back_populates="job", lazy="selectin") # type: ignore
    
    reports: Mapped[list["Report"]] = relationship("ResearchReport", back_populates="job", lazy="selectin") # type: ignore
    
    optimistic_args: Mapped[list["Optimist"]] = relationship("Optimist", back_populates="job", lazy="selectin") # type: ignore
    
    skeptical_args: Mapped[list["Skeptic"]] = relationship("Skeptic", back_populates="job", lazy="selectin") # type: ignore
    
    verdicts: Mapped[list["Verdict"]] = relationship("Verdict", back_populates="job", lazy="selectin") # type: ignore
    
    