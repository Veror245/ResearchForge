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
    
    