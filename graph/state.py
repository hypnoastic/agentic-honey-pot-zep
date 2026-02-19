"""
LangGraph state schema for the Agentic Honey-Pot system.
Defines the shared state that flows through all agents.
"""

import time
from typing import TypedDict, List, Optional, Dict, Any, Annotated
from agents.entity_utils import merge_entities


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
    conversation_id: str

    # Scam Detection Results
    scam_detected: bool
    scam_type: Optional[str]
    scam_indicators: List[str]

    # Engagement State
    persona_name: str
    persona_traits: Dict[str, Any]
    persona_context: str
    conversation_history: List[ConversationTurn]
    engagement_count: int
    max_engagements: int
    engagement_complete: bool

    # Scoring Tracking (NEW — needed for rubric Category 3)
    questions_asked: int         # Total "?" questions honeypot has asked
    red_flags_mentioned: int     # Times "suspicious/red flag/unusual" mentioned
    elicitation_attempts: int    # Explicit requests for specific data fields

    # Engagement Timing (NEW — needed for rubric Category 4)
    engagement_start_time: float  # unix timestamp set at workflow start

    # Extracted Intelligence (all 8 types)
    extracted_entities: Annotated[Dict[str, List[Any]], merge_entities]
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
    planner_action: Optional[str]   # "engage", "judge", "end"
    strategy_hint: Optional[str]    # Guidance for persona

    # Agentic Judge State
    judge_verdict: Optional[str]    # "GUILTY", "INNOCENT", "SUSPICIOUS"
    judge_reasoning: Optional[str]

    # Memory Context
    prior_context: Optional[str]
    prior_scam_types: List[str]
    winning_strategies: List[str]
    past_failures: List[str]
    scam_stats: Dict[str, Any]
    temporal_stats: Dict[str, Any]
    familiarity_score: float
    behavioral_signals: List[str]
    prior_messages: List[Dict[str, Any]]

    # Internet Verification
    fact_check_results: Dict[str, Any]

    # Pre-Filter Results
    prefilter_result: Dict[str, Any]
    prefilter_entities: Dict[str, Any]


def create_initial_state(
    message: str,
    max_engagements: int = 10,
    conversation_id: str = "",
    memory_context: Optional[Dict[str, Any]] = None
) -> HoneypotState:
    """
    Create initial state for a new honeypot workflow.
    """
    import uuid

    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    memory = memory_context or {}
    prior_entities = memory.get("prior_entities", {})

    # All 8 entity types initialized empty
    blank_entities: Dict[str, list] = {
        "bank_accounts": [],
        "upi_ids": [],
        "phishing_urls": [],
        "phone_numbers": [],
        "ifsc_codes": [],
        "email_addresses": [],
        "case_ids": [],
        "policy_numbers": [],
        "order_numbers": [],
    }
    # Merge prior entities if present
    for key in blank_entities:
        prior_val = prior_entities.get(key, [])
        if prior_val:
            blank_entities[key] = list(prior_val)

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

        # Scoring tracking
        questions_asked=memory.get("questions_asked", 0),
        red_flags_mentioned=memory.get("red_flags_mentioned", 0),
        elicitation_attempts=memory.get("elicitation_attempts", 0),

        # Timing — load from memory or generate at session start
        engagement_start_time=memory.get("engagement_start_time") or time.time(),

        # Extraction
        extracted_entities=blank_entities,
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

        # Planner
        planner_action=None,
        strategy_hint=None,

        # Judge
        judge_verdict=None,
        judge_reasoning=None,

        # Memory Context
        prior_context=memory.get("conversation_summary", ""),
        prior_scam_types=memory.get("prior_scam_types", []),
        winning_strategies=memory.get("winning_strategies", []),
        past_failures=memory.get("past_failures", []),
        scam_stats=memory.get("scam_stats", {}),
        temporal_stats=memory.get("temporal_stats", {}),
        familiarity_score=memory.get("familiarity_score", 0.0),
        behavioral_signals=memory.get("behavioral_signals", []),
        prior_messages=memory.get("prior_messages", [])[:10],

        # Internet Verification
        fact_check_results={},

        # Pre-Filter
        prefilter_result={},
        prefilter_entities={},
    )
