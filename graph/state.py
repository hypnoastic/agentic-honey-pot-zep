"""
LangGraph state schema for the Agentic Honey-Pot system.
Defines the shared state that flows through all agents.
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
    conversation_id: str  # Unique ID for the conversation
    
    # Scam Detection Results
    scam_detected: bool
    scam_type: Optional[str]
    scam_indicators: List[str]
    
    # Engagement State
    persona_name: str
    persona_traits: Dict[str, Any] # New: Dynamic Vector
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
    
    # Memory Context (injected from prior conversations)
    prior_context: Optional[str]
    prior_scam_types: List[str]
    winning_strategies: List[str]
    past_failures: List[str]
    scam_stats: Dict[str, Any]
    temporal_stats: Dict[str, Any]
    familiarity_score: float
    behavioral_signals: List[str]
    prior_messages: List[Dict[str, Any]]
    
    # Internet Verification (Serper Fact-Checker)
    fact_check_results: Dict[str, Any]
    
    # Pre-Filter Results (Deterministic)
    prefilter_result: Dict[str, Any]
    prefilter_entities: Dict[str, Any]
    
    # System Mode
    callback_sent: bool



def create_initial_state(
    message: str, 
    max_engagements: int = 5,
    conversation_id: str = "",
    memory_context: Optional[Dict[str, Any]] = None
) -> HoneypotState:
    """
    Create initial state for a new honeypot workflow.
    
    Args:
        message: The incoming message to analyze
        max_engagements: Maximum number of engagement turns with scammer
        conversation_id: Unique conversation identifier
        memory_context: Pre-loaded memory context from PostgreSQL
        
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
        persona_name=memory.get("persona_name", ""),
        persona_traits=memory.get("persona_traits", {}),
        persona_context=memory.get("persona_context", ""),
        conversation_history=[],
        engagement_count=memory.get("engagement_count", 0),
        max_engagements=max_engagements,
        engagement_complete=memory.get("engagement_complete", False),
        
        # Extraction (merge with prior entities - include ALL entity types)
        extracted_entities={
            "bank_accounts": prior_entities.get("bank_accounts", []),
            "upi_ids": prior_entities.get("upi_ids", []),
            "phishing_urls": prior_entities.get("phishing_urls", []),
            "phone_numbers": prior_entities.get("phone_numbers", []),
            "ifsc_codes": prior_entities.get("ifsc_codes", [])
        },
        extraction_complete=False,
        callback_sent=memory.get("callback_sent", False),
        
        # Scoring
        confidence_score=0.0,
        confidence_factors={},
        
        # Output
        conversation_summary="",
        final_response=None,
        
        # Control
        current_agent="scam_detection",
        error=None,
        
        # Memory Context
        prior_context=memory.get("conversation_summary", ""),
        prior_scam_types=memory.get("prior_scam_types", []),
        winning_strategies=memory.get("winning_strategies", []),
        past_failures=memory.get("past_failures", []),
        scam_stats=memory.get("scam_stats", {}),
        temporal_stats=memory.get("temporal_stats", {}),
        familiarity_score=memory.get("familiarity_score", 0.0),
        behavioral_signals=memory.get("behavioral_signals", []),
        prior_messages=memory.get("prior_messages", [])[:10]  # Last 10 messages
    )
