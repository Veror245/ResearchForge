from enum import Enum
from uuid import UUID
from sqlalchemy import String, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.research_finding import ResearchFinding
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

    findings: Mapped[list["ResearchFinding"]] = relationship(
        "ResearchFinding", back_populates="task", lazy="selectin"
    )