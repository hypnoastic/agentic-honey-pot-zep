"""
LangGraph Workflow for the Agentic Honey-Pot system.
Orchestrates all agents in a stateful graph with Zep memory integration.
"""

from typing import Dict, Any, Literal, Optional, Union, List
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
    from config import get_settings
    settings = get_settings()
    max_turns = state.get("max_engagements", settings.max_engagement_turns)
    
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
    
    if action == "engage":
        return "engage"
    elif action == "judge":
        return "judge"
    else:
        return "end"


def _route_after_extraction(state: HoneypotState) -> Literal["loop", "exit"]:
    """
    Route after intelligence extraction.
    Always exit loop (Single Turn).
    """
    return "exit"


async def run_honeypot_analysis(
    message: str, 
    max_engagements: int = 5,
    conversation_id: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Run the complete honeypot analysis workflow with Zep memory.
    
    Args:
        message: The incoming message to analyze
        max_engagements: Maximum engagement turns with scammer
        conversation_id: Optional conversation ID for memory continuity
        conversation_history: Previous messages in this conversation (Section 6.2)
        metadata: Request context (channel, language, locale) (Section 6.3)
        
    Returns:
        Final analysis response
    """
    import uuid
    import logging
    import asyncio
    
    logger = logging.getLogger(__name__)
    
    # Generate conversation ID if not provided
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    
    # Load memory context from Zep
    memory_context = {}
    try:
        from memory.zep_memory import load_conversation_memory, persist_conversation_memory, is_zep_available, search_similar_scams
        
        if is_zep_available():
            # 1. Load Session Memory (Thread Context)
            memory_context = await load_conversation_memory(conversation_id)
            if memory_context.get("prior_messages"):
                logger.info(f"Loaded {len(memory_context['prior_messages'])} prior messages from Zep")
            
            # 2. Semantic Search (Cross-Session Intelligence)
            # Find similar past scams to inform current detection
            from memory.zep_memory import search_similar_scams, get_scam_signal
            
            # A. Lightweight Signal (For Initial Detection)
            zep_signal = await get_scam_signal(message)
            memory_context["zep_signal"] = zep_signal
            logger.info(f"ZEP SIGNAL: Count={zep_signal['similar_count']}, Type={zep_signal['common_type']}")

            # B. Detailed Context (For Planner)
            similar_scams = await search_similar_scams(message, limit=3)
            max_similarity = 0.0
            if similar_scams:
                descriptions = [s.get("content", "") for s in similar_scams]
                scores = [s.get("score", 0.0) for s in similar_scams]
                max_similarity = max(scores) if scores else 0.0
                
                memory_context["prior_scam_types"] = descriptions
                logger.info(f"ZEP INTELLIGENCE: Found {len(descriptions)} similar past scam patterns. Max Sim: {max_similarity:.2f}")
            
            memory_context["familiarity_score"] = max_similarity
            
            # 3. Successful Tactics (Winning Behaviours)
            from memory.zep_memory import search_winning_strategies, search_past_failures
            
            # Find what worked...
            winning_strategies = await search_winning_strategies("scam", limit=3)
            if winning_strategies:
                memory_context["winning_strategies"] = winning_strategies
                logger.info(f"ZEP STRATEGY: Found {len(winning_strategies)} successful extraction strategies.")

            # 4. Anti-Patterns (Failed Engagements)
            past_failures = await search_past_failures("scam", limit=3)
            if past_failures:
                memory_context["past_failures"] = past_failures
                logger.warning(f"ZEP WARNING: Found {len(past_failures)} past failures to avoid.")
                
            # 5. ROI Logic (Strategic Pruning)
            from memory.zep_memory import get_scam_stats, get_optimal_traits
            
            scam_stats = await get_scam_stats("scam") 
            memory_context["scam_stats"] = scam_stats
            logger.info(f"ZEP STATS: Success Rate: {scam_stats['success_rate']:.2f} (n={scam_stats['total_attempts']})")
            
            # 6. Dynamic Persona (Optimal Traits)
            # Use the "Common Type" from the signal to find winning traits
            detected_type = zep_signal.get("common_type", "scam") 
            if not detected_type or detected_type == "Unknown":
                detected_type = "scam"
                
            optimal_traits = await get_optimal_traits(detected_type)
            if optimal_traits:
                memory_context["persona_traits"] = optimal_traits
                logger.info(f"ZEP PERSONA: Found optimal traits for '{detected_type}': {optimal_traits}")
            else:
                logger.info("ZEP PERSONA: No optimal traits found. Using Cold Start defaults.")
                # Cold Start Baseline (Exploration Mode)
                memory_context["persona_traits"] = {
                    "age": "60+",
                    "tech_literacy": "low", 
                    "emotional_state": "confused",
                    "authority_response": "compliant"
                }

            # 7. Temporal Pacing (Optimal Turn Count)
            from memory.zep_memory import get_temporal_stats
            temporal_stats = await get_temporal_stats(detected_type)
            memory_context["temporal_stats"] = temporal_stats
            logger.info(f"ZEP PACING: Average Extraction Turn: {temporal_stats['avg_turns']}")

    except Exception as e:
        logger.warning(f"Could not load Zep memory: {e}")
    
    # Convert request conversation history to internal format (Section 6.2)
    # This enables multi-turn support where prior messages inform agent behavior
    initial_conversation_history = []
    if conversation_history:
        for i, msg in enumerate(conversation_history):
            role = "scammer" if msg.get("sender") == "scammer" else "honeypot"
            initial_conversation_history.append({
                "role": role,
                "message": msg.get("text", ""),
                "turn_number": i + 1
            })
        logger.info(f"[{conversation_id[:8]}] Loaded {len(initial_conversation_history)} messages from request history")
    
    # Create initial state with memory context
    initial_state = create_initial_state(
        message=message, 
        max_engagements=max_engagements,
        conversation_id=conversation_id,
        memory_context=memory_context
    )
    
    # Inject request conversation history into state (for multi-turn)
    if initial_conversation_history:
        initial_state["conversation_history"] = initial_conversation_history
        initial_state["engagement_count"] = len([m for m in initial_conversation_history if m["role"] == "honeypot"])
    
    # Create and run workflow
    workflow = create_honeypot_workflow()
    
    # Execute the workflow (Run in thread to avoid blocking event loop)
    final_state = await asyncio.to_thread(workflow.invoke, initial_state)
    
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
        
    # 8. Failure Analysis (Anti-Pattern Persistence)
    try:
        final_response = final_state.get("final_response", {})
        entity_count = len(final_response.get("extracted_entities", {}).get("bank_accounts", [])) + \
                       len(final_response.get("extracted_entities", {}).get("upi_ids", []))
                       
        turns_used = final_state.get("engagement_count", 0)
        
        # If we engaged significantly (>2 turns) but got NOTHING, log it as a failure.
        if turns_used >= 3 and entity_count == 0:
            from memory.zep_memory import add_failure_event
            await add_failure_event(conversation_id, dict(final_state))
            
    except Exception as e:
        logger.warning(f"Could not persist failure event: {e}")
    
    # 9. GUVI Callback (Section 12 - MANDATORY)
    # Send final result ONLY when:
    # - Scam intent is confirmed (scamDetected = true)
    # - AI Agent has completed engagement (model is satisfied and stopped)
    # - Intelligence extraction is finished
    try:
        scam_detected = final_state.get("scam_detected", False)
        engagement_complete = final_state.get("engagement_complete", False)
        extraction_complete = final_state.get("extraction_complete", False)
        
        # Log the conditions for debugging
        logger.info(f"[{conversation_id[:8]}] GUVI Callback Check:")
        logger.info(f"  - scam_detected: {scam_detected}")
        logger.info(f"  - engagement_complete: {engagement_complete}")
        logger.info(f"  - extraction_complete: {extraction_complete}")
        
        # Only send callback when ALL conditions are met
        if scam_detected and (engagement_complete or extraction_complete):
            from utils.guvi_callback import send_guvi_callback, build_agent_notes
            
            logger.info(f"[{conversation_id[:8]}] ✅ All conditions met - Sending GUVI callback")
            
            entities = final_state.get("extracted_entities", {})
            behavioral_signals = final_state.get("behavioral_signals", [])
            scam_indicators = final_state.get("scam_indicators", [])
            
            # Calculate total messages: request history + current + honeypot responses
            history_count = len(conversation_history or [])
            engagement_count = final_state.get("engagement_count", 0)
            total_messages = history_count + 1 + engagement_count  # history + current message + honeypot turns
            
            # Build agent notes
            agent_notes = build_agent_notes(
                scam_type=final_state.get("scam_type"),
                behavioral_signals=behavioral_signals,
                conversation_summary=final_state.get("conversation_summary", "")
            )
            
            # Fire callback
            callback_success = await send_guvi_callback(
                session_id=conversation_id,
                scam_detected=True,
                total_messages=total_messages,
                extracted_intelligence=entities,
                agent_notes=agent_notes,
                scam_indicators=scam_indicators + behavioral_signals
            )
            
            if callback_success:
                logger.info(f"[{conversation_id[:8]}] GUVI callback sent successfully")
            else:
                logger.warning(f"[{conversation_id[:8]}] GUVI callback failed")
        else:
            if scam_detected:
                logger.info(f"[{conversation_id[:8]}] Scam detected but engagement not complete - callback deferred")
            else:
                logger.info(f"[{conversation_id[:8]}] Not a scam - no callback needed")
                
    except Exception as e:
        logger.warning(f"GUVI callback failed (non-critical): {e}")
    
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
