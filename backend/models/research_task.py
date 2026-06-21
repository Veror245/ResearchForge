from enum import Enum
from uuid import UUID
from sqlalchemy import ForeignKey, String, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.claims import Claim
# from .research_finding import ResearchFinding
from .base import Base, TimestampMixin, generate_uuid
import uuid as _uuid

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class ResearchTask(Base, TimestampMixin):
    __tablename__ = "research_tasks"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=generate_uuid
    )
    query: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False
    )
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="SET NULL"), nullable=True
    )

    job: Mapped["ResearchJob | None"] = relationship("ResearchJob", back_populates="tasks") # type: ignore

    findings: Mapped[list["ResearchFinding"]] = relationship( # type: ignore
        "ResearchFinding", back_populates="task", lazy="selectin"
    )
    
    reports: Mapped[list["ResearchReport"]] = relationship("ResearchReport", back_populates="task", lazy="selectin") # type: ignore
    
    claims: Mapped[list["Claim"]] = relationship("Claim", back_populates="task", lazy="selectin")
    
    critiques: Mapped[list["Critique"]] = relationship("Critique", back_populates="task", lazy="selectin") # type: ignore