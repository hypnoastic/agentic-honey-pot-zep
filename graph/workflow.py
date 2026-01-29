"""
LangGraph Workflow for the Agentic Honey-Pot system.
Orchestrates all agents in a stateful graph with Zep memory integration.
"""

from typing import Dict, Any, Literal, Optional
from langgraph.graph import StateGraph, END

from graph.state import HoneypotState, create_initial_state
from agents.scam_detection import scam_detection_agent
from agents.persona_engagement import persona_engagement_agent
from agents.intelligence_extraction import intelligence_extraction_agent
from agents.confidence_scoring import confidence_scoring_agent
from agents.response_formatter import response_formatter_agent


def create_honeypot_workflow() -> StateGraph:
    """
    Create the LangGraph workflow for the honeypot system.
    
    Flow:
    1. Scam Detection → (if scam) Persona Engagement → Intelligence Extraction
                      → (if not scam) Response Formatter
    2. Persona Engagement loops until max turns or extraction complete
    3. Intelligence Extraction → Confidence Scoring → Response Formatter
    
    Returns:
        Compiled StateGraph workflow
    """
    
    # Create the graph
    workflow = StateGraph(HoneypotState)
    
    # Add nodes for each agent
    workflow.add_node("scam_detection", _scam_detection_node)
    workflow.add_node("persona_engagement", _persona_engagement_node)
    workflow.add_node("intelligence_extraction", _intelligence_extraction_node)
    workflow.add_node("confidence_scoring", _confidence_scoring_node)
    workflow.add_node("response_formatter", _response_formatter_node)
    
    # Set entry point
    workflow.set_entry_point("scam_detection")
    
    # Add conditional edges from scam_detection
    workflow.add_conditional_edges(
        "scam_detection",
        _route_after_detection,
        {
            "engage": "persona_engagement",
            "format": "response_formatter"
        }
    )
    
    # Add conditional edges from persona_engagement
    workflow.add_conditional_edges(
        "persona_engagement",
        _route_after_engagement,
        {
            "continue": "persona_engagement",
            "extract": "intelligence_extraction"
        }
    )
    
    # Linear flow for remaining nodes
    workflow.add_edge("intelligence_extraction", "confidence_scoring")
    workflow.add_edge("confidence_scoring", "response_formatter")
    workflow.add_edge("response_formatter", END)
    
    return workflow.compile()


def _scam_detection_node(state: HoneypotState) -> HoneypotState:
    """Execute scam detection agent."""
    result = scam_detection_agent(dict(state))
    return {**state, **result}


def _persona_engagement_node(state: HoneypotState) -> HoneypotState:
    """Execute persona engagement agent."""
    result = persona_engagement_agent(dict(state))
    return {**state, **result}


def _intelligence_extraction_node(state: HoneypotState) -> HoneypotState:
    """Execute intelligence extraction agent."""
    result = intelligence_extraction_agent(dict(state))
    return {**state, **result}


def _confidence_scoring_node(state: HoneypotState) -> HoneypotState:
    """Execute confidence scoring agent."""
    result = confidence_scoring_agent(dict(state))
    return {**state, **result}


def _response_formatter_node(state: HoneypotState) -> HoneypotState:
    """Execute response formatter agent."""
    result = response_formatter_agent(dict(state))
    return {**state, **result}


def _route_after_detection(state: HoneypotState) -> Literal["engage", "format"]:
    """
    Route based on scam detection result.
    If scam detected, engage with persona. Otherwise, format response directly.
    """
    if state.get("scam_detected", False):
        return "engage"
    return "format"


def _route_after_engagement(state: HoneypotState) -> Literal["continue", "extract"]:
    """
    Route based on engagement state.
    Continue engagement if not complete and under max turns.
    """
    if state.get("engagement_complete", False):
        return "extract"
    
    engagement_count = state.get("engagement_count", 0)
    max_engagements = state.get("max_engagements", 5)
    
    if engagement_count < max_engagements:
        return "continue"
    
    return "extract"


async def run_honeypot_analysis(
    message: str, 
    max_engagements: int = 5,
    conversation_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run the complete honeypot analysis workflow with Zep memory.
    
    Args:
        message: The incoming message to analyze
        max_turns: Maximum engagement turns with scammer
        conversation_id: Optional conversation ID for memory continuity
        
    Returns:
        Final analysis response
    """
    import uuid
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Generate conversation ID if not provided
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    
    # Load memory context from Zep
    memory_context = {}
    try:
        from memory.zep_memory import load_conversation_memory, persist_conversation_memory, is_zep_available
        
        if is_zep_available():
            memory_context = await load_conversation_memory(conversation_id)
            if memory_context.get("prior_messages"):
                logger.info(f"Loaded {len(memory_context['prior_messages'])} prior messages from Zep")
    except Exception as e:
        logger.warning(f"Could not load Zep memory: {e}")
    
    # Create initial state with memory context
    initial_state = create_initial_state(
        message=message, 
        max_engagements=max_engagements,
        conversation_id=conversation_id,
        memory_context=memory_context
    )
    
    # Create and run workflow
    workflow = create_honeypot_workflow()
    
    # Execute the workflow
    final_state = workflow.invoke(initial_state)
    
    # Persist results to Zep memory
    try:
        from memory.zep_memory import persist_conversation_memory, is_zep_available
        
        if is_zep_available():
            await persist_conversation_memory(
                conversation_id=conversation_id,
                state=dict(final_state),
                is_final=True
            )
            logger.info(f"Persisted conversation to Zep session {conversation_id}")
    except Exception as e:
        logger.warning(f"Could not persist to Zep memory: {e}")
    
    # Return the final response
    return final_state.get("final_response", {
        "is_scam": False,
        "scam_type": None,
        "confidence_score": 0.0,
        "extracted_entities": {
            "bank_accounts": [],
            "upi_ids": [],
            "phishing_urls": []
        },
        "conversation_summary": "Analysis failed to complete."
    })
