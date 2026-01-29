"""
Pydantic schemas for request/response validation.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Request schema for the /analyze endpoint."""
    message: str = Field(
        ...,
        description="The incoming message to analyze for scam detection",
        min_length=1,
        max_length=10000
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Optional conversation ID for multi-turn memory continuity"
    )



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
    conversation_summary: str = Field(
        default="",
        description="Concise summary of the scam engagement conversation"
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Conversation ID for multi-turn continuity (use in subsequent requests)"
    )



class ScammerMessage(BaseModel):
    """Message from Mock Scammer API."""
    message: str = Field(..., description="Scammer's response message")
    revealed_info: Optional[dict] = Field(
        default=None,
        description="Information revealed by scammer in this turn"
    )


class EngagementRequest(BaseModel):
    """Request to Mock Scammer API for engagement."""
    victim_message: str = Field(..., description="Message from the honeypot persona")
    conversation_id: str = Field(..., description="Unique conversation identifier")
    turn_number: int = Field(..., description="Current turn in the conversation")
