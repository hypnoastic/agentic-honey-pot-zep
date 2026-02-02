"""
LangGraph state schema for the Agentic Honey-Pot system.
Defines the shared state that flows through all agents.
Includes Zep memory context fields.
"""

from typing import TypedDict, List, Optional, Dict, Any
from models.schemas import ExtractedEntities


class ConversationTurn(TypedDict):
    """Single turn in the conversation with scammer."""
    role: str  # "honeypot" or "scammer"
    message: str
    turn_number: int


class HoneypotState(TypedDict):
    """
    Shared state for the honeypot workflow.
    This state is passed through all agents and updated incrementally.
    """
    # Input
    original_message: str
    conversation_id: str  # Unique ID for Zep session
    
    # Scam Detection Results
    scam_detected: bool
    scam_type: Optional[str]
    scam_indicators: List[str]
    
    # Engagement State
    persona_name: str
    persona_context: str
    conversation_history: List[ConversationTurn]
    engagement_count: int
    max_engagements: int
    engagement_complete: bool
    
    # Extracted Intelligence
    extracted_entities: Dict[str, List[str]]
    extraction_complete: bool
    
    # Scoring
    confidence_score: float
    confidence_factors: Dict[str, float]
    
    # Final Output
    conversation_summary: str
    final_response: Optional[Dict[str, Any]]
    
    # Control Flow
    current_agent: str
    error: Optional[str]
    
    # Planner State
    planner_action: Optional[str]  # "engage", "judge", "end"
    strategy_hint: Optional[str]   # Guidance for persona (e.g., "Play dumb")
    
    # Agentic Judge State
    judge_verdict: Optional[str]   # "GUILTY", "INNOCENT", "SUSPICIOUS"
    judge_reasoning: Optional[str] # Text explanation
    
    # Zep Memory Context (injected from prior conversations)
    prior_context: Optional[str]
    prior_scam_types: List[str]
    behavioral_signals: List[str]
    prior_messages: List[Dict[str, Any]]
    zep_enabled: bool
    
    # System Mode
    execution_mode: str  # "simulation" or "live"


def create_initial_state(
    message: str, 
    max_engagements: int = 5,
    conversation_id: str = "",
    memory_context: Optional[Dict[str, Any]] = None,
    execution_mode: str = "simulation"
) -> HoneypotState:
    """
    Create initial state for a new honeypot workflow.
    
    Args:
        message: The incoming message to analyze
        max_engagements: Maximum number of engagement turns with scammer
        conversation_id: Unique conversation identifier for Zep session
        memory_context: Pre-loaded memory context from Zep
        execution_mode: "simulation" (loop with mock) or "live" (single turn)
        
    Returns:
        Initialized HoneypotState
    """
    import uuid
    
    # Generate conversation ID if not provided
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    
    # Extract memory context values
    memory = memory_context or {}
    prior_entities = memory.get("prior_entities", {
        "bank_accounts": [],
        "upi_ids": [],
        "phishing_urls": []
    })
    
    return HoneypotState(
        # Input
        original_message=message,
        conversation_id=conversation_id,
        
        # Scam Detection
        scam_detected=False,
        scam_type=None,
        scam_indicators=[],
        
        # Engagement
        persona_name="",
        persona_context="",
        conversation_history=[],
        engagement_count=0,
        max_engagements=max_engagements,
        engagement_complete=False,
        
        # Extraction (merge with prior entities)
        extracted_entities={
            "bank_accounts": prior_entities.get("bank_accounts", []),
            "upi_ids": prior_entities.get("upi_ids", []),
            "phishing_urls": prior_entities.get("phishing_urls", [])
        },
        extraction_complete=False,
        
        # Scoring
        confidence_score=0.0,
        confidence_factors={},
        
        # Output
        conversation_summary="",
        final_response=None,
        
        # Control
        current_agent="scam_detection",
        error=None,
        
        # Zep Memory Context
        prior_context=memory.get("conversation_summary", ""),
        prior_scam_types=memory.get("prior_scam_types", []),
        behavioral_signals=memory.get("behavioral_signals", []),
        prior_messages=memory.get("prior_messages", [])[:10],  # Last 10 messages
        zep_enabled=bool(memory),
        
        # System Mode
        execution_mode=execution_mode
    )
