from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Text, ForeignKey
from .base import Base, TimestampMixin, generate_uuid

from pydantic import BaseModel, Field
from typing import List, Optional

from uuid import UUID

class Skeptic(Base, TimestampMixin):
    __tablename__ = "skeptical_claims"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=generate_uuid)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    
    arguements: Mapped[str] = mapped_column(Text, nullable=False)

    job: Mapped["ResearchJob"] = relationship(back_populates="skeptical_args") # type: ignore

class Optimist(Base, TimestampMixin):
    __tablename__ = "optimistic_claims"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=generate_uuid)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    
    arguements: Mapped[str] = mapped_column(Text, nullable=False)

    job: Mapped["ResearchJob"] = relationship(back_populates="optimistic_args") # type: ignore
 
    
class SkepticSchema(BaseModel):
    claim: str = Field(
        description="The claim text"
    )
    evidence: Optional[str] = Field(
        description="Optional evidence or rationale supporting the skeptical arguments"
    )
    arguements: str = Field(
        description="List of skeptical arguments against the claim"
    )

class OptimistSchema(BaseModel):
    claim: str = Field(
        description="The claim text"
    )
    evidence: Optional[str] = Field(
        description="Optional evidence or rationale supporting the optimistic arguments"
    )
    arguements: str = Field(
        description="List of optimistic arguments for the claim"
    )
    
class SkepticalClaimsResponse(BaseModel):
    skeptical_claims: List[SkepticSchema] = Field(
        description="List of skeptical claims extracted from the document"
    )

class OptimisticClaimsResponse(BaseModel):
    optimistic_claims: List[OptimistSchema] = Field(
        description="List of optimistic claims extracted from the document"
    )

class DebateOutput(BaseModel):
    skeptic_arguments: list[SkepticSchema]
    optimist_arguments: list[OptimistSchema]