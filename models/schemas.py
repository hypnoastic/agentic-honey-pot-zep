"""
Pydantic schemas for request/response validation.
Aligned with official scoring rubric output format.
"""

from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
import time


class HackathonMessage(BaseModel):
    """Message structure used by Hackathon Tester."""
    sender: Optional[str] = None
    text: Optional[str] = None
    timestamp: Optional[int] = None


class ConversationMessage(BaseModel):
    """Message in conversation history (Section 6.2)."""
    sender: str  # "scammer" or "user"
    text: str
    timestamp: Optional[int] = None


class RequestMetadata(BaseModel):
    """Metadata about the request context (Section 6.3)."""
    model_config = ConfigDict(extra="ignore")

    channel: Optional[str] = None  # SMS / WhatsApp / Email / Chat
    language: Optional[str] = None
    locale: Optional[str] = None


class AnalyzeRequest(BaseModel):
    """Request schema for the /analyze endpoint (Section 6)."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    message: Optional[Union[str, HackathonMessage, Dict[str, Any]]] = Field(
        default="",
        description="The incoming message to analyze (string or object)"
    )
    conversation_id: Optional[str] = Field(
        default=None,
        alias="sessionId",  # Support both sessionId and conversation_id
        description="Session ID for multi-turn conversation continuity"
    )
    conversation_history: List[ConversationMessage] = Field(
        default_factory=list,
        alias="conversationHistory",
        description="Previous messages in this conversation (empty for first message)"
    )
    metadata: Optional[RequestMetadata] = Field(
        default=None,
        description="Optional context metadata (channel, language, locale)"
    )


# =============================================================================
# EXTRACTED INTELLIGENCE — 8 types as required by scoring rubric
# =============================================================================

class ExtractedIntelligence(BaseModel):
    """
    All 8 intelligence entity types required by the scoring rubric.
    Exact field names match the rubric spec.
    """
    phoneNumbers: List[str] = Field(default_factory=list)
    bankAccounts: List[str] = Field(default_factory=list)
    upiIds: List[str] = Field(default_factory=list)
    phishingLinks: List[str] = Field(default_factory=list)
    emailAddresses: List[str] = Field(default_factory=list)
    caseIds: List[str] = Field(default_factory=list)
    policyNumbers: List[str] = Field(default_factory=list)
    orderNumbers: List[str] = Field(default_factory=list)


# =============================================================================
# FINAL RESPONSE — Exact format required by scoring rubric section 5
# =============================================================================

class HoneypotResponse(BaseModel):
    """
    Official response format matching the scoring rubric exactly.
    Required fields: sessionId, scamDetected, extractedIntelligence
    Optional (bonus): engagementMetrics, agentNotes, scamType, confidenceLevel
    """
    model_config = ConfigDict(populate_by_name=True)

    # Required (2 pts each = 6 pts)
    sessionId: str = Field(default="", description="Session UUID")
    scamDetected: bool = Field(default=False, description="Whether a scam was detected")
    extractedIntelligence: ExtractedIntelligence = Field(
        default_factory=ExtractedIntelligence,
        description="Gathered intelligence from conversation"
    )

    # Optional bonus fields (1 pt each = 4 pts)
    engagementDurationSeconds: float = Field(default=0.0, description="Engagement duration in seconds")
    totalMessagesExchanged: int = Field(default=0, description="Total number of messages exchanged")
    agentNotes: Optional[str] = Field(default=None, description="Summary of scammer behavior")
    scamType: Optional[str] = Field(default=None, description="Type of scam detected")
    confidenceLevel: Optional[float] = Field(default=None, description="Detection confidence 0.0-1.0")

    # Internal fields (not scored but useful for debugging / backward compat)
    reply: Optional[str] = Field(default=None, description="Agent's reply to the scammer")
    status: str = Field(default="success", description="Response status")


# =============================================================================
# BACKWARD COMPATIBILITY — Keep AnalyzeResponse aliased for old code paths
# =============================================================================

class ExtractedEntities(BaseModel):
    """Internal entity format (used in old code paths)."""
    bank_accounts: List[str] = Field(default_factory=list)
    upi_ids: List[str] = Field(default_factory=list)
    phishing_urls: List[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    """
    Legacy response schema — kept for backward compatibility.
    New code should use HoneypotResponse instead.
    """
    status: str = Field(default="success")
    reply: Optional[str] = Field(default=None)
    scam_detected: Optional[bool] = Field(default=False)
    scam_type: Optional[str] = Field(default=None)
    extracted_entities: Optional[Dict[str, List[Any]]] = Field(default_factory=dict)
    engagement_count: Optional[int] = Field(default=0)
    strategy_hint: Optional[str] = Field(default=None)
