"""
LangGraph Workflow for the Agentic Honey-Pot system.
Orchestrates all agents in a stateful graph with PostgreSQL memory integration.

HARDENED ARCHITECTURE:
1. Pre-Filter (deterministic) → routes obvious scams directly to Planner
2. Scam Detection (LLM) → only for ambiguous cases
3. Planner (LLM) → includes verdict when action=judge (merged Judge)
4. Intelligence Extraction → regex-first, LLM-verify

EXPORTS:
- run_honeypot_workflow: Main async function
- run_honeypot_analysis: Alias for backward compatibility
"""

import logging
from typing import Dict, Any, Literal, Optional, Union, List
from langgraph.graph import StateGraph, END

from graph.state import HoneypotState, create_initial_state
from agents.scam_detection import scam_detection_agent
from agents.planner import planner_agent
from agents.persona_engagement import persona_engagement_agent
from agents.intelligence_extraction import intelligence_extraction_agent
from agents.response_formatter import response_formatter_agent
from memory.postgres_memory import capture_session_lock

logger = logging.getLogger(__name__)


def create_honeypot_workflow() -> StateGraph:
    """
    Create the LangGraph workflow for the honeypot system.
    
    HARDENED FLOW:
    1. Pre-Filter (deterministic) → obvious scam skips LLM detection
    2. Scam Detection (LLM) → only for ambiguous cases
    3. Planner → (Engage | End)  [Judge merged into Planner]
    4. Engage → Persona → Extraction → loop or exit
    """
    
    # Create the graph
    workflow = StateGraph(HoneypotState)
    
    # Add nodes
    # Add nodes
    workflow.add_node("pre_filter", _pre_filter_node)
    workflow.add_node("scam_detection", _scam_detection_node)
    workflow.add_node("planner", _planner_node)
    workflow.add_node("persona_engagement", _persona_engagement_node)
    workflow.add_node("intelligence_extraction", _intelligence_extraction_node)  # Full LLM
    workflow.add_node("regex_extractor", _regex_extractor_node)                  # Fast Regex
    workflow.add_node("response_formatter", _response_formatter_node)
    
    # Set entry point
    workflow.set_entry_point("pre_filter")
    
    # Conditional Edge: Pre-Filter → Scam Detection OR Planner
    workflow.add_conditional_edges(
        "pre_filter",
        _route_from_prefilter,
        {
            "obvious_scam": "planner",
            "needs_llm": "scam_detection"
        }
    )
    
    # Edge: Detection → Planner
    workflow.add_edge("scam_detection", "planner")
    
    # Conditional Edge: Planner → Next Step
    workflow.add_conditional_edges(
        "planner",
        _route_from_planner,
        {
            "engage": "persona_engagement",
            "judge": "intelligence_extraction",  # Judge -> Deep Scan
            "end": "response_formatter"          # End -> Skip Scan
        }
    )
    
    # Edge: Persona → Regex Extractor (Fast Loop)
    workflow.add_edge("persona_engagement", "regex_extractor")
    
    # Edge: Regex Extractor → Formatter
    workflow.add_edge("regex_extractor", "response_formatter")

    # Edge: Full Extraction → Formatter
    workflow.add_edge("intelligence_extraction", "response_formatter")
    
    # Edge: Formatter → End
    workflow.add_edge("response_formatter", END)
    
    return workflow.compile()


def _pre_filter_node(state: HoneypotState) -> HoneypotState:
    """
    Deterministic pre-filter node.
    Detects obvious scams without LLM call.
    """
    from utils.prefilter import prefilter_scam_detection, extract_entities_deterministic
    
    message = state.get("original_message", "")
    
    # Run deterministic scam detection
    is_obvious, scam_type, confidence, indicators = prefilter_scam_detection(message)
    
    # Run deterministic entity extraction
    regex_entities = extract_entities_deterministic(message)
    
    logger.info(f"PRE-FILTER: Obvious={is_obvious}, Type={scam_type}, Conf={confidence:.2f}")
    
    if is_obvious:
        # FAST PATH: Skip LLM detection entirely
        return {
            **state,
            "prefilter_result": {
                "is_obvious": True,
                "scam_type": scam_type,
                "confidence": confidence,
                "indicators": indicators
            },
            "scam_detected": True,
            "scam_type": scam_type,
            "scam_indicators": indicators,
            "confidence_score": confidence,
            "prefilter_entities": regex_entities,
            "current_agent": "planner"
        }
    else:
        # SLOW PATH: Needs LLM analysis
        return {
            **state,
            "prefilter_result": {
                "is_obvious": False,
                "scam_type": scam_type,
                "confidence": confidence,
                "indicators": indicators
            },
            "prefilter_entities": regex_entities,
            "current_agent": "scam_detection"
        }


def _scam_detection_node(state: HoneypotState) -> HoneypotState:
    result = scam_detection_agent(dict(state))
    return {**state, **result}


def _planner_node(state: HoneypotState) -> HoneypotState:
    result = planner_agent(dict(state))
    return {**state, **result}


def _persona_engagement_node(state: HoneypotState) -> HoneypotState:
    state["strategy_hint"] = state.get("strategy_hint", "")
    result = persona_engagement_agent(dict(state))
    return {**state, **result}


def _intelligence_extraction_node(state: HoneypotState) -> HoneypotState:
    result = intelligence_extraction_agent(dict(state))
    return {**state, **result}


def _regex_extractor_node(state: HoneypotState) -> HoneypotState:
    """Node for fast regex-only extraction."""
    from agents.intelligence_extraction import regex_only_extraction_agent
    result = regex_only_extraction_agent(dict(state))
    return {**state, **result}


def _response_formatter_node(state: HoneypotState) -> HoneypotState:
    result = response_formatter_agent(dict(state))
    return {**state, **result}


def _route_from_prefilter(state: HoneypotState) -> Literal["obvious_scam", "needs_llm"]:
    """Route based on pre-filter result."""
    prefilter = state.get("prefilter_result", {})
    
    if prefilter.get("is_obvious", False):
        logger.info("PRE-FILTER ROUTE: Obvious scam detected, skipping LLM")
        return "obvious_scam"
    else:
        logger.info("PRE-FILTER ROUTE: Ambiguous, forwarding to LLM detection")
        return "needs_llm"


def _route_from_planner(state: HoneypotState) -> Literal["engage", "judge", "end"]:
    """Route based on Planner's decision."""
    action = state.get("planner_action", "end")
    
    # Safety Check: If max turns reached, force judge (not end, to capture info)
    count = state.get("engagement_count", 0)
    from config import get_settings
    settings = get_settings()
    max_turns = state.get("max_engagements", settings.max_engagement_turns)
    
    if count >= max_turns and action == "engage":
        logger.info(f"PLANNER ROUTE: Max turns ({max_turns}) reached, forcing Judge")
        return "judge"
    
    if action == "engage":
        return "engage"
    elif action == "judge":
        return "judge"
    else:
        return "end"


# ============================================================================
# ASYNC WORKFLOW RUNNER
# ============================================================================

import asyncio
import uuid

async def run_honeypot_workflow(
    message: str,
    conversation_id: Optional[str] = None,
    max_engagements: int = 12,
    conversation_history: Optional[List[Dict]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Run the complete honeypot workflow asynchronously.
    
    Args:
        message: The message to analyze
        conversation_id: Unique conversation ID
        max_engagements: Maximum engagement turns
        conversation_history: Prior conversation history
        metadata: Optional metadata from API request
    """
    
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    
    logger.info(f"[{conversation_id[:8]}] Starting honeypot workflow")
    
    # Initialize memory context
    memory_context = {}
    
    # Try to load context from Postgres
    # Acquire session lock to serialize requests for same ID
    async with capture_session_lock(conversation_id) as txn_conn:
        
        # Try to load context from Postgres
        try:
            from memory.postgres_memory import (
                load_conversation_memory,
                get_scam_signal,
                search_similar_scams,
                search_winning_strategies,
                search_past_failures,
                get_scam_stats,
                get_optimal_traits,
                get_temporal_pacing
            )
            
            if True:
                # BATCH 1: Independent queries + Fact-Check (all in parallel)
                from agents.fact_checker import fact_check_message
                
                # We need to pass txn_conn to load_conversation_memory
                batch1_results = await asyncio.gather(
                    load_conversation_memory(conversation_id, conn=txn_conn),
                    # Note: get_scam_signal functionality is merged into search_similar_scams or handled via Postgres
                    # but we keep the structure for now if it exists in postgres_memory
                    search_similar_scams(message, limit=3),
                    search_winning_strategies("scam", limit=3),
                    search_past_failures("scam", limit=3),
                    get_scam_stats("scam"),
                    fact_check_message(message),
                    return_exceptions=True
                )
                
                # Unpack results
                session_memory, similar_scams, winning_strategies, past_failures, scam_stats, fact_check_results = batch1_results
                
                # Handle exceptions gracefully
                if isinstance(session_memory, Exception):
                    session_memory = {}
                if isinstance(similar_scams, Exception):
                    similar_scams = []
                if isinstance(winning_strategies, Exception):
                    winning_strategies = []
                if isinstance(past_failures, Exception):
                    past_failures = []
                if isinstance(scam_stats, Exception):
                    scam_stats = {"success_rate": 0.5, "total_attempts": 0}
                if isinstance(fact_check_results, Exception):
                    fact_check_results = {"fact_checked": False, "reason": "Fact-check failed"}
                
                # Build memory context
                memory_context = session_memory if isinstance(session_memory, dict) else {}
                memory_context["fact_check_results"] = fact_check_results
                
                if similar_scams:
                    descriptions = [s.get("content", "") for s in similar_scams]
                    scores = [s.get("score", 0.0) for s in similar_scams]
                    max_similarity = max(scores) if scores else 0.0
                    memory_context["prior_scam_types"] = descriptions
                    memory_context["familiarity_score"] = max_similarity
                
                if winning_strategies:
                    memory_context["winning_strategies"] = winning_strategies
                
                if past_failures:
                    memory_context["past_failures"] = past_failures
                
                memory_context["scam_stats"] = scam_stats
                
                if fact_check_results.get("fact_checked"):
                    logger.info(f"FACT-CHECK: {fact_check_results.get('overall_status', 'UNKNOWN')}")
                
                # BATCH 2: Dependent queries
                # Use most similar scam type for optimization if available
                detected_type = "scam"
                if similar_scams and isinstance(similar_scams, list) and len(similar_scams) > 0:
                     # Extract type from metadata or content if possible
                     pass
                
                batch2_results = await asyncio.gather(
                    get_optimal_traits(detected_type),
                    get_temporal_pacing(detected_type),
                    return_exceptions=True
                )
                
                optimal_traits, temporal_stats = batch2_results
                
                if isinstance(optimal_traits, Exception):
                    optimal_traits = None
                if isinstance(temporal_stats, Exception):
                    temporal_stats = {"avg_turns": 4.0, "sample_size": 0}
                
                if not memory_context.get("persona_traits"):
                    if optimal_traits:
                        memory_context["persona_traits"] = optimal_traits
                    else:
                        memory_context["persona_traits"] = {
                            "age": "60+",
                            "tech_literacy": "low",
                            "emotional_state": "confused",
                            "authority_response": "compliant"
                        }
                
                memory_context["temporal_stats"] = temporal_stats

        except Exception as e:
            logger.warning(f"Could not load memory: {e}")
        
        # Convert conversation history
        initial_conversation_history = []
        if conversation_history:
            for i, msg in enumerate(conversation_history):
                role = "scammer" if msg.get("sender") == "scammer" else "honeypot"
                initial_conversation_history.append({
                    "role": role,
                    "message": msg.get("text", ""),
                    "turn_number": i + 1
                })
        
        # Create initial state
        initial_state = create_initial_state(
            message=message,
            max_engagements=max_engagements,
            conversation_id=conversation_id,
            memory_context=memory_context
        )
        
        if not initial_conversation_history and memory_context.get("prior_messages"):
            for i, msg in enumerate(memory_context["prior_messages"]):
                role = "honeypot" if msg.get("role") == "assistant" else "scammer"
                initial_conversation_history.append({
                    "role": role,
                    "message": msg.get("content", ""),
                    "turn_number": i + 1
                })

        if initial_conversation_history:
            initial_state["conversation_history"] = initial_conversation_history
            # Use persisted count if available, otherwise calculate
            persisted_count = memory_context.get("engagement_count", 0)
            calculated_count = len([m for m in initial_conversation_history if m["role"] == "honeypot"])
            initial_state["engagement_count"] = max(persisted_count, calculated_count)
            
            # Restore completion flags
            initial_state["engagement_complete"] = memory_context.get("engagement_complete", False)
            initial_state["extraction_complete"] = memory_context.get("extraction_complete", False)
            initial_state["scam_detected"] = memory_context.get("scam_detected", False)
        
        # Create and run workflow
        workflow = create_honeypot_workflow()
        
        final_state = await asyncio.to_thread(workflow.invoke, initial_state)
        
        # Persist results to Postgres
        try:
            from memory.postgres_memory import persist_conversation_memory
            
            if True:
                await persist_conversation_memory(
                    conversation_id=conversation_id,
                    state=dict(final_state),
                    is_final=True,
                    conn=txn_conn
                )
        except Exception as e:
            logger.warning(f"Could not persist memory: {e}")
        
        # Failure Analysis
        try:
            final_response = final_state.get("final_response", {})
            entity_count = len(final_response.get("extracted_entities", {}).get("bank_accounts", [])) + \
                           len(final_response.get("extracted_entities", {}).get("upi_ids", []))
            
            turns_used = final_state.get("engagement_count", 0)
            
            if turns_used >= 3 and entity_count == 0:
                from memory.postgres_memory import add_failure_event
                await add_failure_event(conversation_id, dict(final_state))
                
        except Exception as e:
            logger.warning(f"Could not persist failure event: {e}")
        
        # GUVI Callback
        try:
            scam_detected = final_state.get("scam_detected", False)
            engagement_complete = final_state.get("engagement_complete", False)
            extraction_complete = final_state.get("extraction_complete", False)
            
            error_present = final_state.get("error") is not None
            
            if scam_detected and (engagement_complete or extraction_complete) and not error_present:
                from utils.guvi_callback import send_guvi_callback, build_agent_notes
                
                entities = final_state.get("extracted_entities", {})
                behavioral_signals = final_state.get("behavioral_signals", [])
                scam_indicators = final_state.get("scam_indicators", [])
                
                history_count = len(conversation_history or [])
                engagement_count = final_state.get("engagement_count", 0)
                total_messages = history_count + 1 + engagement_count
                
                agent_notes = build_agent_notes(
                    scam_type=final_state.get("scam_type"),
                    behavioral_signals=behavioral_signals,
                    conversation_summary=final_state.get("conversation_summary", "")
                )
                
                await send_guvi_callback(
                    session_id=conversation_id,
                    scam_detected=True,
                    total_messages=total_messages,
                    extracted_intelligence=entities,
                    agent_notes=agent_notes,
                    scam_indicators=scam_indicators + behavioral_signals
                )
                    
        except Exception as e:
            logger.warning(f"GUVI callback failed: {e}")
        
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


# ============================================================================
# BACKWARD COMPATIBILITY ALIAS
# ============================================================================

# Alias for main.py compatibility
run_honeypot_analysis = run_honeypot_workflow
