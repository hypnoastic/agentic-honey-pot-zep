"""
Pydantic schemas for request/response validation.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Request schema for the /analyze endpoint."""
    message: Optional[str] = Field(
        default="",
        description="The incoming message to analyze for scam detection",
        max_length=10000
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Optional conversation ID for multi-turn memory continuity"
    )

    class Config:
        extra = "ignore"


class ExtractedEntities(BaseModel):
    """Extracted intelligence entities from scam interaction."""
    bank_accounts: List[str] = Field(
        default_factory=list,
        description="List of extracted bank account numbers"
    )
    upi_ids: List[str] = Field(
        default_factory=list,
        description="List of extracted UPI IDs (format: xxx@provider)"
    )
    phishing_urls: List[str] = Field(
        default_factory=list,
        description="List of extracted phishing/suspicious URLs"
    )


class AnalyzeResponse(BaseModel):
    """Response schema for the /analyze endpoint."""
    is_scam: bool = Field(
        ...,
        description="Whether the message was detected as a scam"
    )
    scam_type: Optional[str] = Field(
        default=None,
        description="Type of scam detected (e.g., UPI_FRAUD, LOTTERY_FRAUD, PHISHING)"
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score of the scam detection (0.0 to 1.0)"
    )
    extracted_entities: ExtractedEntities = Field(
        default_factory=ExtractedEntities,
        description="Extracted intelligence from scam engagement"
    )
    behavioral_signals: List[str] = Field(
        default_factory=list,
        description="Psychological triggers identified (e.g. Urgency, Greed)"
    )
    confidence_factors: dict = Field(
        default_factory=dict,
        description="Breakdown of confidence score factors"
    )

    agent_reply: Optional[str] = Field(
        default=None,
        description="The immediate reply to send to the scammer (Live Mode only)"
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Conversation ID for multi-turn continuity (use in subsequent requests)"
    )
