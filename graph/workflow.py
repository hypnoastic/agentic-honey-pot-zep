"""
LangGraph Workflow for the Agentic Honey-Pot system.
Orchestrates all agents in a stateful graph with Zep memory integration.
"""

from typing import Dict, Any, Literal, Optional
from langgraph.graph import StateGraph, END

from graph.state import HoneypotState, create_initial_state
from agents.scam_detection import scam_detection_agent
from agents.planner import planner_agent
from agents.persona_engagement import persona_engagement_agent
from agents.intelligence_extraction import intelligence_extraction_agent
from agents.judge import agentic_judge_agent
from agents.response_formatter import response_formatter_agent


def create_honeypot_workflow() -> StateGraph:
    """
    Create the LangGraph workflow for the honeypot system.
    
    New Flow (Agentic):
    1. Scam Detection -> Planner
    2. Planner -> (Engage | Judge | End)
    3. Engage -> Persona -> Extraction -> Planner
    4. Judge -> Response Formatter
    """
    
    # Create the graph
    workflow = StateGraph(HoneypotState)
    
    # Add nodes
    workflow.add_node("scam_detection", _scam_detection_node)
    workflow.add_node("planner", _planner_node)
    workflow.add_node("persona_engagement", _persona_engagement_node)
    workflow.add_node("intelligence_extraction", _intelligence_extraction_node)
    workflow.add_node("agentic_judge", _agentic_judge_node)
    workflow.add_node("response_formatter", _response_formatter_node)
    
    # Set entry point
    workflow.set_entry_point("scam_detection")
    
    # Edge: Detection -> Planner
    workflow.add_edge("scam_detection", "planner")
    
    # Conditional Edge: Planner -> Next Step
    workflow.add_conditional_edges(
        "planner",
        _route_from_planner,
        {
            "engage": "persona_engagement",
            "judge": "agentic_judge",
            "end": "response_formatter"
        }
    )
    
    # Conditional Edge from Intelligence Extraction
    # Live Mode: Exit to Formatter (Single Turn)
    # Simulation: Loop back to Planner
    workflow.add_conditional_edges(
        "intelligence_extraction",
        _route_after_extraction,
        {
            "loop": "planner",
            "exit": "response_formatter"
        }
    )
    
    # Loop: Engagement -> Extraction
    workflow.add_edge("persona_engagement", "intelligence_extraction")
    
    # Edge: Judge -> Formatter
    workflow.add_edge("agentic_judge", "response_formatter")
    
    # Edge: Formatter -> End
    workflow.add_edge("response_formatter", END)
    
    return workflow.compile()


def _scam_detection_node(state: HoneypotState) -> HoneypotState:
    result = scam_detection_agent(dict(state))
    return {**state, **result}

def _planner_node(state: HoneypotState) -> HoneypotState:
    result = planner_agent(dict(state))
    return {**state, **result}

def _persona_engagement_node(state: HoneypotState) -> HoneypotState:
    # Inject strategy hint from planner
    state["strategy_hint"] = state.get("strategy_hint", "")
    result = persona_engagement_agent(dict(state))
    return {**state, **result}

def _intelligence_extraction_node(state: HoneypotState) -> HoneypotState:
    result = intelligence_extraction_agent(dict(state))
    return {**state, **result}

def _agentic_judge_node(state: HoneypotState) -> HoneypotState:
    result = agentic_judge_agent(dict(state))
    return {**state, **result}

def _response_formatter_node(state: HoneypotState) -> HoneypotState:
    result = response_formatter_agent(dict(state))
    return {**state, **result}


def _route_from_planner(state: HoneypotState) -> Literal["engage", "judge", "end"]:
    """Route based on Planner's decision."""
    action = state.get("planner_action", "judge")
    
    # Safety Check: If max turns reached, force judge
    count = state.get("engagement_count", 0)
    max_turns = state.get("max_engagements", 5)
    
    if count >= max_turns and action == "engage":
        return "judge"
        
    # In Live Mode, we break the loop after one engagement cycle
    # But the Planner is smart now.
    # If Planner says "engage", we go Engage -> Extract -> Planner.
    # The Loop logic handles the "Live Mode Single Turn" exit inside Schema/API response,
    # BUT we need to ensure we don't loop infinitely in a single API call if logic is weird.
    # Actually, for Live Mode, we want: Detection -> Planner -> Engage -> Extract -> Formatter -> EXIT.
    # We shouldn't loop back to Planner in Live Mode?
    # Correct. In LIVE mode, we do ONE step.
    
    if state.get("execution_mode") == "live":
        if action == "engage":
            return "engage"
        elif action == "judge":
            return "judge"
        else:
            return "end"

    return action


def _route_after_engagement(state: HoneypotState):
    # This logic is now handled by the Planner loop
    pass

def _route_after_extraction(state: HoneypotState) -> Literal["loop", "exit"]:
    """
    Route after intelligence extraction.
    Live Mode: Exit loop (Single Turn).
    Simulation Mode: Loop back to Planner.
    """
    if state.get("execution_mode") == "live":
        return "exit"
        
    if state.get("engagement_complete", False):
        return "exit"
        
    return "loop"


async def run_honeypot_analysis(
    message: str, 
    max_engagements: int = 5,
    conversation_id: Optional[str] = None,
    execution_mode: str = "simulation"
) -> Dict[str, Any]:
    """
    Run the complete honeypot analysis workflow with Zep memory.
    
    Args:
        message: The incoming message to analyze
        max_turns: Maximum engagement turns with scammer
        conversation_id: Optional conversation ID for memory continuity
        execution_mode: "simulation" or "live"
        
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
        memory_context=memory_context,
        execution_mode=execution_mode
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
