"""
Planner Agent (with merged Judge functionality)
"The Mastermind"
Decides the high-level strategy, next action, AND final verdict.

RESPONSIBILITIES:
- Decide action: engage/judge/end
- Provide strategy hints for persona
- When action=judge: output verdict, confidence, reasoning

NOT RESPONSIBLE FOR:
- Entity extraction (handled by Intelligence Extraction)
- Regex scanning (handled by Pre-Filter + Intelligence Extraction)
"""

import json
import logging
from typing import Dict, Any, Optional
from utils.llm_client import call_llm

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """STRATEGIC PLANNER: Waste time AND extract intelligence (Bank, UPI, URL, Phone).
GOAL: High-efficiency extraction (3-4 turns target).

CURRENT STATE:
- Scam Detected: {scam_detected}
- Scam Type: {scam_type}
- Turns Used: {turns_used}/{max_turns}
- Extracted Entities: {extracted_count}

PACING ADVICE (TEMPORAL LEARNING):
{temporal_pacing_info}

FAMILIARITY SCORE (SEMANTIC CLUSTERING):
{familiarity_score:.2f}/1.0. (Logic: <0.6 = NOVEL/EXPLORE, >0.8 = KNOWN/EXECUTE)

CONVERSATION HISTORY (Last 3 turns):
{recent_history}

WINNING TACTICS (From past successful extractions):
{winning_strategies}

FAILED STRATEGIES (TO AVOID):
{past_failures}

LATEST SCAMMER MESSAGE:
"{latest_message}"

EXTRACTED EVIDENCE:
- Bank Accounts: {bank_accounts}
- UPI IDs: {upi_ids}
- URLs: {phishing_urls}
- Scam Indicators: {scam_indicators}

DECISION LOGIC:
1. "engage": Stall/Waste time. Ask for verification, payment details, or official links.
2. "judge": Conclude if: Key info extracted, Max turns reached, or Scammer stopped.
3. "end": Only if NOT a scam.

DIVERSITY EXIT: Prioritize getting different types (UPI+Bank+URL) over count.
Target 3-4 focused turns.

Respond with JSON ONLY:
{{
    "action": "engage" | "judge" | "end",
    "strategy_hint": "Brief guidance for the persona...",
    "verdict": "GUILTY" | "INNOCENT" | "SUSPICIOUS" | null,
    "confidence_score": 0.0-1.0 | null,
    "reasoning": "Explanation of verdict..." | null
}}"""


def planner_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decide the next action and strategy.
    When action=judge, also outputs verdict, confidence, and reasoning.
    
    READS from state (does NOT perform extraction):
    - extracted_entities: Set by Intelligence Extraction agent
    - scam_detected, scam_type: Set by Scam Detection / Pre-filter
    - conversation_history: Accumulated history
    """
    logger.info("Planner Agent: Analyzing strategy...")
    
    # Initialize defaults to prevent UnboundLocalError
    max_turns = 10
    turns_used = 0
    high_value_count = 0
    total_entities = 0
    distinct_types = 0
    
    # Prepare inputs
    history = state.get("conversation_history", [])
    recent_history = ""
    for turn in history[-3:]:
        role = "Honeypot" if turn["role"] == "honeypot" else "Scammer"
        recent_history += f"{role}: {turn['message']}\n"

    last_message = state.get("original_message", "")
    if history and history[-1]["role"] == "scammer":
        last_message = history[-1]["message"]

    # =========================================================================
    # PHASE 1: HARDEN DEFINITIONS & INVARIANTS
    # =========================================================================
    from config import get_settings
    settings = get_settings()
    
    # 1. Strict Turn Cap (HARD CAP 10)
    max_turns = min(10, state.get("max_engagements", settings.max_engagement_turns))
    turns_used = max(0, state.get("engagement_count", 0))
    
    # Invariant Check: Prevent infinite loops or negative turns
    if turns_used < 0:
        logger.error(f"INVARIANT VIOLATION: Negative turns_used ({turns_used}). Resetting to 0.")
        turns_used = 0
    
    # 2. Safe Entity Definitions
    entities = state.get("extracted_entities", {})
    if not isinstance(entities, dict):
        logger.error(f"TYPE ERROR: extracted_entities is {type(entities)}, expected dict. Defaulting to empty.")
        entities = {}
        
    bank_list = [e.get("value", e) if isinstance(e, dict) else e for e in entities.get("bank_accounts", [])]
    upi_list = [e.get("value", e) if isinstance(e, dict) else e for e in entities.get("upi_ids", [])]
    url_list = [e.get("value", e) if isinstance(e, dict) else e for e in entities.get("phishing_urls", [])]
    phone_list = [e.get("value", e) if isinstance(e, dict) else e for e in entities.get("phone_numbers", [])]
    
    # 3. High-Value Derived Stats
    high_value_count = len(bank_list) + len(upi_list) + len(url_list)
    total_entities = high_value_count + len(phone_list)
    
    # Calculate Identity Diversity
    distinct_types = 0
    if bank_list: distinct_types += 1
    if upi_list: distinct_types += 1
    if url_list: distinct_types += 1
    if phone_list: distinct_types += 1
    
    # Invariant Check: Diversity max is 4
    if distinct_types > 4:
        logger.warning(f"INVARIANT WARNING: distinct_types ({distinct_types}) > 4 categories. Capping at 4.")
        distinct_types = 4
    
    logger.info(f"Planner [Hardened]: Turn {turns_used}/{max_turns}, Yield: {high_value_count} (across {distinct_types} types), Total: {total_entities}")

    # =========================================================================
    # DYNAMIC EXIT POLICY (Diversity Aware)
    # =========================================================================
    should_complete, completion_reason = _check_smart_exit(
        high_value_count, total_entities, turns_used, max_turns, distinct_types
    )
    
    if should_complete:
        logger.info(f"POLICY EXIT TRIGGERED: {completion_reason}")
        
        # Determine verdict based on evidence strength and diversity
        verdict, confidence, reasoning = _determine_verdict(
            state, entities, high_value_count, distinct_types
        )
            
        from utils.logger import AgentLogger
        AgentLogger.plan_decision(
            current_turn=turns_used,
            max_turns=max_turns,
            decision="judge",
            reasoning=f"POLICY EXIT: {completion_reason}"
        )
        
        return {
            "planner_action": "judge",
            "strategy_hint": completion_reason,
            "judge_verdict": verdict,
            "confidence_score": confidence,
            "judge_reasoning": reasoning,
            "scam_detected": verdict in ["GUILTY", "SUSPICIOUS"],
            "engagement_complete": True,
            "extraction_complete": True,
            "current_agent": "planner"
        }
    
    # =========================================================================
    # LLM-BASED PLANNING
    # =========================================================================
    winning_tactics = state.get("winning_strategies", [])
    tactics_str = "- " + "\n- ".join(winning_tactics) if winning_tactics else "No specific tactics."

    failures = state.get("past_failures", [])
    failures_str = "- " + "\n- ".join(failures) if failures else "No failures to avoid."

    # Temporal Pacing
    temporal = state.get("temporal_stats", {})
    avg_turns = temporal.get("avg_turns", 4.0)
    sample_size = temporal.get("sample_size", 0)
    
    if sample_size > 2:
        if turns_used < avg_turns - 1:
            pacing_info = f"AVG SUCCESS AT TURN {avg_turns}. Currently Turn {turns_used}. STALL."
        elif turns_used >= avg_turns:
            pacing_info = f"AVG SUCCESS AT TURN {avg_turns}. Currently Turn {turns_used}. EXTRACT NOW."
        else:
            pacing_info = f"Approaching optimal turn ({avg_turns}). Prepare to pivot."
    else:
        pacing_info = "No historical pacing data. Use judgement."

    prompt = PLANNER_PROMPT.format(
        scam_detected=state.get("scam_detected", False),
        scam_type=state.get("scam_type", "Unknown"),
        turns_used=turns_used,
        max_turns=max_turns,
        extracted_count=high_value_count,
        temporal_pacing_info=pacing_info,
        familiarity_score=state.get("familiarity_score", 0.0),
        recent_history=recent_history or "No history yet",
        winning_strategies=tactics_str,
        past_failures=failures_str,
        latest_message=last_message,
        bank_accounts=bank_list[:3],
        upi_ids=upi_list[:3],
        phishing_urls=url_list[:3],
        scam_indicators=state.get("scam_indicators", [])[:5]
    )

    try:
        response_text = call_llm(
            prompt=prompt,
            system_instruction="You are a strategic AI planner for a scambaiting system.",
            json_mode=True,
            agent_name="planner"
        )
        
        plan = json.loads(response_text)
        action = plan.get("action", "judge")
        hint = plan.get("strategy_hint", "Continue engagement")
        
        # Extract verdict if action is judge
        verdict = plan.get("verdict")
        confidence = plan.get("confidence_score")
        reasoning = plan.get("reasoning")
        
        from utils.logger import AgentLogger
        AgentLogger.plan_decision(
            current_turn=turns_used,
            max_turns=max_turns,
            decision=action,
            reasoning=hint
        )
        
        result = {
            "planner_action": action,
            "strategy_hint": hint,
            "current_agent": "planner"
        }
        
        # If judging, include verdict
        if action == "judge":
            result["judge_verdict"] = verdict or "SUSPICIOUS"
            result["confidence_score"] = float(confidence) if confidence else 0.7
            result["judge_reasoning"] = reasoning or "Concluded based on evidence."
            result["scam_detected"] = verdict in ["GUILTY", "SUSPICIOUS", None]
            result["engagement_complete"] = True
            result["extraction_complete"] = True
        
        return result

    except Exception as e:
        logger.error(f"Planner failed: {e}")
        return {
            "planner_action": "judge",
            "strategy_hint": "Error in planning, finishing up.",
            "judge_verdict": "SUSPICIOUS",
            "confidence_score": 0.5,
            "judge_reasoning": f"Planner error: {e}",
            "engagement_complete": True,
            "error": str(e)
        }


def _check_smart_exit(high_value: int, total: int, turns: int, max_turns: int, distinct_types: int) -> tuple:
    """
    Refined Diversity-Aware Exit Strategy:
    - Turn 0:    >=3 high-value AND >=2 distinct types
    - Turn 1-2:  >=3 high-value
    - Turn 3-4:  >=3 high-value OR (>=2 high-value AND >=2 distinct types)
    - Turn 5-6:  >=2 high-value
    - Turn 7-9:  >=1 high-value
    - Turn 10+:  Force exit
    """
    if turns >= 10:
        return True, f"Max turns reached ({turns}). Forced exit."
    
    if turns == 0:
        if high_value >= 3 and distinct_types >= 2:
            return True, f"T0: High-density/diversity yield ({high_value} entities, {distinct_types} types)."
    elif 1 <= turns <= 2:
        if high_value >= 3:
            return True, f"T{turns}: High-yield lead ({high_value} entities)."
    elif 3 <= turns <= 4:
        if high_value >= 3 or (high_value >= 2 and distinct_types >= 2):
            return True, f"T{turns}: Significant yield ({high_value} entities, {distinct_types} types)."
    elif 5 <= turns <= 6:
        if high_value >= 2:
            return True, f"T{turns}: Sufficient yield ({high_value} entities)."
    elif 7 <= turns <= 9:
        if high_value >= 1:
            return True, f"T{turns}: Lead secured ({high_value} entity)."
            
    return False, ""


def _determine_verdict(state: Dict, entities: Dict, high_value: int, distinct_types: int) -> tuple:
    """
    Evidence-based verdict calibration (Hardened).
    Confidence derived from: Detection status, Count, Diversity, and Indicators.
    
    Guards:
    - If scam_detected is False, verdict can NEVER be GUILTY.
    - Confidence is strictly capped at 0.99.
    """
    scam_detected = state.get("scam_detected", False)
    scam_type = state.get("scam_type", "Unknown")
    indicators = state.get("scam_indicators", [])
    
    # 1. Base Verdict Determination
    if not scam_detected and not indicators and high_value == 0:
        return "INNOCENT", 0.5, "No evidence of scam detected by system sensors."

    # 2. Base Confidence [0.4 - 0.6]
    # Detection is the strongest signal, but not sufficient for 0.9+ alone
    base_confidence = 0.65 if scam_detected else 0.45
    
    # 3. Evidence Strength Boosts (Additive)
    # Diversity: 0.05 per extra category (up to +0.2)
    diversity_bonus = min(0.2, (distinct_types - 1) * 0.07) if distinct_types > 0 else 0
    
    # Count: 0.03 per high-value entity (up to +0.15)
    count_bonus = min(0.15, high_value * 0.03)
    
    # Indicators: 0.01 per indicator (up to +0.05)
    indicator_bonus = min(0.05, len(indicators) * 0.01)
    
    # Final Calculation
    raw_confidence = base_confidence + diversity_bonus + count_bonus + indicator_bonus
    confidence = max(0.0, min(0.99, raw_confidence))
    
    # 4. Final Verdict and Detection Guard
    if confidence >= 0.8:
        verdict = "GUILTY"
    elif confidence >= 0.6:
        verdict = "SUSPICIOUS"
    else:
        verdict = "INNOCENT"
        
    # DETECTION GUARD: If system didn't flag it as a scam, we cannot declare it GUILTY
    if not scam_detected and verdict == "GUILTY":
        logger.warning("DETECTION GUARD: Confidence suggested GUILTY but scam_detected is False. Downgrading to SUSPICIOUS.")
        verdict = "SUSPICIOUS"
        confidence = min(0.79, confidence)
        
    reasoning = (f"Hardened Confidence {confidence:.2f} | "
                 f"Detection: {scam_detected} ({scam_type}) | "
                 f"Yield: {high_value} entities ({distinct_types} categories) | "
                 f"Indicators: {len(indicators)}")
                 
    return verdict, confidence, reasoning
