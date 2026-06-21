from pydantic import BaseModel, Field
from enum import Enum


class ClaimType(str, Enum):
    FACT = "fact"
    DECISION = "decision"
    METRIC = "metric"
    RELATIONSHIP = "relationship"
    REQUIREMENT = "requirement"
    LIMITATION = "limitation"

class Claim(BaseModel):
    claim: str = Field(
        description="A single extracted claim"
    )

    evidence: str = Field(
        description="Evidence from the source text supporting the claim"
    )

    confidence: float = Field(
        ge=0,
        le=1,
        description="How strongly the source text supports this claim"
    )

    importance: float = Field(
        ge=0,
        le=10,
        description="Importance of the claim for understanding the document"
    )
    
    type: ClaimType = Field(
        description="The type of claim, such as fact, decision, metric, etc."
    )
    
    chunk: str | None = Field(
        default=None,
        description="Optional chunk of text from which the claim was extracted"
    )

class ClaimsResponse(BaseModel):
    claims: list[Claim] = Field(
        description="List of extracted claims from the document, MAXIMUM 5 CLAIMS, NO MORE THAN 5 CLAIMS"
    )
    
