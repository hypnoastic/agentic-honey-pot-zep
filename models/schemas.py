"""
Pydantic schemas for request/response validation.
Aligned with problem statement Sections 6, 7, and 8.
"""

from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


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


class ExtractedEntities(BaseModel):
    """Extracted intelligence entities from scam interaction (internal use for GUVI callback)."""
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
    """
    Response schema for the /analyze endpoint (Section 8).
    
    Minimal response format as required by problem statement:
    {"status": "success", "reply": "..."}
    """
    status: str = Field(
        default="success",
        description="Response status (success/error)"
    )
    reply: Optional[str] = Field(
        default=None,
        description="The agent's reply to send to the scammer"
    )


