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
import asyncio
import uuid
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
    """
    workflow = StateGraph(HoneypotState)
    
    # Add nodes
    workflow.add_node("parallel_intake", _parallel_intake_node)
    workflow.add_node("planner", _planner_node)
    workflow.add_node("persona_engagement", _persona_engagement_node)
    workflow.add_node("intelligence_extraction", _intelligence_extraction_node)
    workflow.add_node("regex_extractor", _regex_extractor_node)
    workflow.add_node("response_formatter", _response_formatter_node)
    
    # Set entry point
    workflow.set_entry_point("parallel_intake")
    
    # Edges
    workflow.add_conditional_edges(
        "parallel_intake",
        _route_from_intake,
        {
            "planner": "planner",
            "end": "response_formatter"
        }
    )
    
    workflow.add_conditional_edges(
        "planner",
        _route_from_planner,
        {
            "engage": "persona_engagement",
            "judge": "intelligence_extraction",
            "end": "response_formatter"
        }
    )
    
    workflow.add_edge("persona_engagement", "regex_extractor")
    workflow.add_edge("regex_extractor", "response_formatter")
    workflow.add_edge("intelligence_extraction", "response_formatter")
    workflow.add_edge("response_formatter", END)
    
    return workflow.compile()


# ============================================================================
# HELPER NODES
# ============================================================================

def _pre_filter_node(state: HoneypotState) -> HoneypotState:
    from utils.prefilter import prefilter_scam_detection, extract_entities_deterministic
    message = state.get("original_message", "")
    is_obvious, scam_type, confidence, indicators = prefilter_scam_detection(message)
    regex_entities = extract_entities_deterministic(message)
    
    logger.info(f"PRE-FILTER: Obvious={is_obvious}, Type={scam_type}")
    
    res = {
        **state,
        "prefilter_result": {"is_obvious": is_obvious, "scam_type": scam_type, "confidence": confidence, "indicators": indicators},
        "prefilter_entities": regex_entities
    }
    
    if is_obvious:
        res.update({
            "scam_detected": True,
            "scam_type": scam_type,
            "scam_indicators": indicators,
            "confidence_score": confidence
        })
    return res

async def _scam_detection_node(state: HoneypotState) -> Dict[str, Any]:
    return await scam_detection_agent(dict(state))

async def _planner_node(state: HoneypotState) -> Dict[str, Any]:
    return await planner_agent(dict(state))

async def _persona_engagement_node(state: HoneypotState) -> Dict[str, Any]:
    return await persona_engagement_agent(dict(state))

async def _intelligence_extraction_node(state: HoneypotState) -> Dict[str, Any]:
    return await intelligence_extraction_agent(dict(state))

async def _regex_extractor_node(state: HoneypotState) -> Dict[str, Any]:
    from agents.intelligence_extraction import regex_only_extraction_agent
    return regex_only_extraction_agent(dict(state))

async def _response_formatter_node(state: HoneypotState) -> Dict[str, Any]:
    return await response_formatter_agent(dict(state))

# ============================================================================
# ORCHESTRATION HELPER NODES
# ============================================================================

async def _parallel_intake_node(state: HoneypotState) -> Dict[str, Any]:
    """Parallel Assessment and Extraction."""
    async def run_assessment():
        # Pre-filter is sync but we call it here
        from utils.prefilter import prefilter_scam_detection, extract_entities_deterministic
        message = state.get("original_message", "")
        is_obvious, scam_type, confidence, indicators = prefilter_scam_detection(message)
        regex_entities = extract_entities_deterministic(message)
        
        pre_res = {
            "prefilter_result": {"is_obvious": is_obvious, "scam_type": scam_type, "confidence": confidence, "indicators": indicators},
            "prefilter_entities": regex_entities
        }
        
        if is_obvious:
            pre_res.update({
                "scam_detected": True,
                "scam_type": scam_type,
                "scam_indicators": indicators,
                "confidence_score": confidence
            })
            return pre_res
        
        # If not obvious, run LLM detection
        # Create a temp state for the agent
        temp_state = {**state, **pre_res}
        detect_res = await scam_detection_agent(temp_state)
        return {**pre_res, **detect_res}

    async def run_extraction():
        return await intelligence_extraction_agent(dict(state))

    assessment_res, extraction_res = await asyncio.gather(run_assessment(), run_extraction())
    
    # Merged deltas
    merged_delta = {**assessment_res, **extraction_res}
    
    # Authoritative Force for entities
    entities = merged_delta.get("extracted_entities", {})
    high_value = len(entities.get("bank_accounts", [])) + len(entities.get("upi_ids", [])) + len(entities.get("phishing_urls", []))
    
    if high_value > 0:
        merged_delta["scam_detected"] = True
        if not merged_delta.get("scam_type"): 
            merged_delta["scam_type"] = "SUSPICIOUS_ENTITY"
        
    return merged_delta

def _route_from_intake(state: HoneypotState) -> Literal["planner", "end"]:
    return "planner" if state.get("scam_detected") else "end"

def _route_from_planner(state: HoneypotState) -> Literal["engage", "end"]:
    """Route from planner. Judge goes directly to end (extraction already done in parallel_intake)."""
    action = state.get("planner_action", "end")
    if action == "judge":
        return "end"  # Skip second extraction, go straight to formatter
    return "engage" if action == "engage" else "end"

# ============================================================================
# SHARED WORKFLOW LOGIC
# ============================================================================

async def _load_system_memory(conversation_id: str, message: str, txn_conn: Any) -> Dict[str, Any]:
    """Helper to load all memory and fact-check data in parallel."""
    try:
        from memory.postgres_memory import (
            load_conversation_memory, search_similar_scams, 
            search_winning_strategies, search_past_failures, 
            get_scam_stats, get_optimal_traits, get_temporal_pacing
        )
        from agents.fact_checker import fact_check_message
        
        # Use default scam_type (will be refined by scam_detection_agent later)
        scam_type = "scam"
        
        # Parallel calls for independent queries (2-4s savings)
        session_mem_task = load_conversation_memory(conversation_id, conn=txn_conn)
        parallel_tasks = asyncio.gather(
            search_similar_scams(message, limit=3),
            search_winning_strategies(scam_type, limit=3),
            search_past_failures(scam_type, limit=3),
            get_scam_stats(scam_type),
            fact_check_message(message)
        )
        
        session_mem = await session_mem_task
        similar, winning, failures, stats, fact_check = await parallel_tasks
        
        ctx = session_mem if isinstance(session_mem, dict) else {}
        ctx["fact_check_results"] = fact_check
        
        if similar:
            scores = [s.get("score", 0.0) for s in similar]
            ctx["prior_scam_types"] = [s.get("content", "") for s in similar]
            ctx["familiarity_score"] = max(scores) if scores else 0.0
            
        ctx.update({"winning_strategies": winning, "past_failures": failures, "scam_stats": stats})
        
        batch2 = await asyncio.gather(
            get_optimal_traits("scam"), get_temporal_pacing("scam"),
            return_exceptions=True
        )
        
        ctx["persona_traits"] = batch2[0] if not isinstance(batch2[0], Exception) else None
        ctx["temporal_stats"] = batch2[1] if not isinstance(batch2[1], Exception) else {"avg_turns": 4.0}
        
        return ctx
    except Exception as e:
        logger.warning(f"Memory orchestration failed: {e}")
        return {"fact_check_results": {"fact_checked": False}}

# ============================================================================
# GUVI CALLBACK WITH RETRY
# ============================================================================

async def _trigger_guvi_callback_with_retry(state: Dict[str, Any], conversation_id: str, max_retries: int = 3):
    """Trigger GUVI callback with exponential backoff retry."""
    import httpx
    from config import get_settings
    settings = get_settings()
    
    # Check if we have sufficient data to trigger callback (log BEFORE URL check)
    entities = state.get("extracted_entities", {})
    high_value_count = sum([
        len(entities.get("upi_ids", [])),
        len(entities.get("phone_numbers", [])),
        len(entities.get("bank_accounts", [])),
        len(entities.get("urls", []))
    ])
    
    extraction_complete = state.get("extraction_complete", False)
    engagement_complete = state.get("engagement_complete", False)
    
    # Log callback decision details
    logger.info(f"🎯 GUVI CALLBACK CHECK: entities={high_value_count} (UPI={len(entities.get('upi_ids', []))}, Phone={len(entities.get('phone_numbers', []))}, Account={len(entities.get('bank_accounts', []))}, URL={len(entities.get('urls', []))}), extraction_complete={extraction_complete}, engagement_complete={engagement_complete}")
    
    if not settings.guvi_callback_url:
        logger.warning("⚠️  GUVI callback skipped: No callback URL configured (set GUVI_CALLBACK_URL in .env)")
        return
    
    # Only trigger if we have completion flags OR sufficient high-value entities (2+)
    if not (extraction_complete or engagement_complete or high_value_count >= 2):
        logger.info(f"GUVI callback skipped: Insufficient data threshold not met")
        return
    
    logger.info(f"✅ Triggering GUVI callback: Sufficient data collected!")
    
    payload = state.get("final_response", {})
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    settings.guvi_callback_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    logger.info(f"GUVI callback successful for {conversation_id}")
                    return
                else:
                    logger.warning(f"GUVI callback returned {response.status_code}")
        except Exception as e:
            wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
            logger.warning(f"GUVI callback attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
    
    logger.error(f"GUVI callback failed after {max_retries} attempts for {conversation_id}")

async def _trigger_guvi_callback_safe(state: Dict[str, Any], conversation_id: str):
    try:
        if state.get("scam_detected") and (state.get("engagement_complete") or state.get("extraction_complete")):
            from utils.guvi_callback import send_guvi_callback, build_agent_notes
            
            notes = build_agent_notes(
                scam_type=state.get("scam_type"),
                behavioral_signals=state.get("behavioral_signals", []),
                conversation_summary=state.get("conversation_summary", "")
            )
            
            await send_guvi_callback(
                session_id=conversation_id,
                scam_detected=True,
                total_messages=len(state.get("conversation_history", [])) + state.get("engagement_count", 0) + 1,
                extracted_intelligence=state.get("extracted_entities", {}),
                agent_notes=notes,
                scam_indicators=state.get("scam_indicators", []) + state.get("behavioral_signals", [])
            )
    except Exception as e:
        logger.warning(f"GUVI callback orchestration failed: {e}")

# ============================================================================
# MAIN WORKFLOW RUNNER
# ============================================================================

async def run_honeypot_workflow(
    message: str,
    conversation_id: Optional[str] = None,
    max_engagements: int = 12,
    conversation_history: Optional[List[Dict]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    
    if not conversation_id: conversation_id = str(uuid.uuid4())
    logger.info(f"[{conversation_id[:8]}] Starting honeypot workflow")
    
    async with capture_session_lock(conversation_id) as txn_conn:
        # 1. Load context
        memory_context = await _load_system_memory(conversation_id, message, txn_conn)
        
        # 2. Build initial state
        initial_history = []
        if conversation_history:
            for i, msg in enumerate(conversation_history):
                initial_history.append({
                    "role": "scammer" if msg.get("sender") == "scammer" else "honeypot",
                    "message": msg.get("text", ""),
                    "turn_number": i + 1
                })
        
        initial_state = create_initial_state(
            message=message,
            max_engagements=max_engagements,
            conversation_id=conversation_id,
            memory_context=memory_context
        )
        
        # Load persona from memory if exists (fixes persona changing every turn)
        if memory_context.get("persona_name"):
            initial_state["persona_name"] = memory_context["persona_name"]
            initial_state["persona_context"] = memory_context.get("persona_context", "{}")
            logger.info(f"Loaded existing persona: {memory_context['persona_name']}")
        
        if initial_history:
            initial_state["conversation_history"] = initial_history
            initial_state["engagement_count"] = len([m for m in initial_history if m["role"] == "honeypot"])
            initial_state["scam_detected"] = memory_context.get("scam_detected", False)

        # 3. Execute Workflow
        workflow = create_honeypot_workflow()
        final_state = await workflow.ainvoke(initial_state)
        
        # 4. Failure Event Logging
        try:
            entity_count = len(final_state.get("extracted_entities", {}).get("bank_accounts", []))
            if final_state.get("engagement_count", 0) >= 3 and entity_count == 0:
                from memory.postgres_memory import add_failure_event
                await add_failure_event(conversation_id, dict(final_state))
        except Exception as e:
            logger.warning(f"Failed to log failure event: {e}")
        
        # 5. Callback with retry
        await _trigger_guvi_callback_with_retry(final_state, conversation_id)
        
        # 6. Database Persistence (Neon) - Intelligence embedding in background
        from memory.postgres_memory import persist_conversation_memory
        is_final = final_state.get("engagement_complete", False) or final_state.get("extraction_complete", False)
        
        # Persist without waiting for intelligence embedding (background task)
        await persist_conversation_memory(
            conversation_id=conversation_id,
            state=final_state,
            is_final=is_final,
            conn=txn_conn,
            background_embedding=True  # Non-blocking embedding
        )
        
        # 6. Final Return
        if "final_response" in final_state:
            return final_state["final_response"]
            
        from utils.safe_response import construct_safe_response
        return construct_safe_response(final_state, conversation_id)

# Backward Compatibility
run_honeypot_analysis = run_honeypot_workflow

# ============================================================================
# CACHED WORKFLOW (Module-level compilation)
# ============================================================================

_COMPILED_WORKFLOW = None

def get_compiled_workflow():
    """Get cached compiled workflow (10-20ms savings per request)."""
    global _COMPILED_WORKFLOW
    if _COMPILED_WORKFLOW is None:
        _COMPILED_WORKFLOW = create_honeypot_workflow()
    return _COMPILED_WORKFLOW
