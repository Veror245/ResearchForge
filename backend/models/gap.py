    

from typing import Text
from uuid import UUID
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, mapped_column

from backend.models.base import Base, TimestampMixin


class GapAnalysis(Base, TimestampMixin):
    __tablename__ = "gap_analyses"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=UUID)
    claim_id: Mapped[UUID] = mapped_column(ForeignKey("claims.id"))
    critique_id: Mapped[UUID] = mapped_column(ForeignKey("critiques.id"))
    task_id: Mapped[UUID] = mapped_column(ForeignKey("research_tasks.id"))
    resolved: Mapped[bool] = mapped_column(default=False)  # True if chunk refutes critique
    follow_up_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_tasks.id"), nullable=True)
    reasoning: Mapped[str] = mapped_column(Text)