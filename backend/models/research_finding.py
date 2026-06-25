from uuid import UUID
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from .research_task import ResearchTask
from pgvector.sqlalchemy import Vector
from .base import Base, TimestampMixin, generate_uuid

class ResearchFinding(Base, TimestampMixin):
    __tablename__ = "research_findings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=generate_uuid)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False
    )
    job_id : Mapped[UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_engine: Mapped[str | None] = mapped_column(String(50), nullable=True)

    embedding = mapped_column(Vector(1536), nullable=True)  # adjust dimension later

    task: Mapped["ResearchTask"] = relationship( # type: ignore
        "ResearchTask", back_populates="findings"
    )
    
    job: Mapped["ResearchJob"] = relationship( # type: ignore
        "ResearchJob", back_populates="findings"
    )
    
    claims: Mapped[list["Claim"]] = relationship("Claim", back_populates="finding", lazy="selectin") # type: ignore
    