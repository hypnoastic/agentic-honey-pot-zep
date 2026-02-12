"""
Planner Agent (Hardened - Core Logic Preserved)

Enhancements:
- LLM schema validation
- Safe action fallback (never default to judge)
- Strict verdict authority enforcement
- Guarded numeric casting
- Indicator dampening (anti-spam)
- Diversity bonus safety check
- Immutable core logic preserved
"""

import json
import logging
from typing import Dict, Any, Tuple
from utils.llm_client import call_llm_async

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = {"engage", "judge", "end"}
ALLOWED_VERDICTS = {"GUILTY", "INNOCENT", "SUSPICIOUS"}

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


async def planner_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("Planner Agent: Analyzing strategy...")

    from config import get_settings
    settings = get_settings()

    # -------------------------------------------------------------------------
    # HARDENED STATE EXTRACTION
    # -------------------------------------------------------------------------

    max_turns = min(10, state.get("max_engagements", settings.max_engagement_turns))
    turns_used = max(0, state.get("engagement_count", 0))

    history = state.get("conversation_history", []) or []
    entities = state.get("extracted_entities", {}) or {}

    if not isinstance(entities, dict):
        logger.error("Invalid extracted_entities type. Resetting.")
        entities = {}

    # -------------------------------------------------------------------------
    # SAFE ENTITY FLATTENING
    # -------------------------------------------------------------------------

    def safe_values(key):
        values = []
        for e in entities.get(key, []):
            if isinstance(e, dict):
                values.append(e.get("value"))
            else:
                values.append(e)
        return [v for v in values if v]

    bank_list = safe_values("bank_accounts")
    upi_list = safe_values("upi_ids")
    url_list = safe_values("phishing_urls")
    phone_list = safe_values("phone_numbers")

    high_value_count = len(bank_list) + len(upi_list) + len(url_list)
    total_entities = high_value_count + len(phone_list)

    distinct_types = sum(bool(lst) for lst in [bank_list, upi_list, url_list, phone_list])
    distinct_types = min(4, distinct_types)

    # -------------------------------------------------------------------------
    # SMART EXIT (UNCHANGED LOGIC)
    # -------------------------------------------------------------------------

    should_complete, completion_reason = _check_smart_exit(
        high_value_count, total_entities, turns_used, max_turns, distinct_types
    )

    if should_complete:
        verdict, confidence, reasoning = _determine_verdict(
            state, entities, high_value_count, distinct_types
        )

        return {
            "planner_action": "judge",
            "strategy_hint": completion_reason,
            "judge_verdict": verdict,
            "confidence_score": confidence,
            "judge_reasoning": reasoning,
            "scam_detected": verdict in {"GUILTY", "SUSPICIOUS"},
            "engagement_complete": True,
            "extraction_complete": True,
            "current_agent": "planner"
        }

    # -------------------------------------------------------------------------
    # LLM PLANNING (HARDENED)
    # -------------------------------------------------------------------------

    prompt = _build_prompt(state, turns_used, max_turns, high_value_count,
                           bank_list, upi_list, url_list)

    try:
        response_text = await call_llm_async(
            prompt=prompt,
            system_instruction="You are a strategic AI planner.",
            json_mode=True,
            agent_name="planner"
        )

        plan = json.loads(response_text)

    except Exception as e:
        logger.error(f"Planner LLM failed: {e}")
        return _safe_fallback()

    # -------------------------------------------------------------------------
    # STRICT SCHEMA ENFORCEMENT
    # -------------------------------------------------------------------------

    action = plan.get("action")
    if action not in ALLOWED_ACTIONS:
        logger.warning(f"Invalid action from LLM: {action}. Defaulting to engage.")
        action = "engage"

    strategy_hint = plan.get("strategy_hint", "Continue engagement.")

    result = {
        "planner_action": action,
        "strategy_hint": strategy_hint,
        "current_agent": "planner"
    }
    
    # Log planner decision for visibility
    logger.info(f"🎯 PLANNER DECISION: action={action}, strategy={strategy_hint[:80]}...")

    # -------------------------------------------------------------------------
    # VERDICT AUTHORITY HARDENING
    # LLM can decide WHEN to judge.
    # System decides WHAT the verdict is.
    # -------------------------------------------------------------------------

    if action == "judge":
        verdict, confidence, reasoning = _determine_verdict(
            state, entities, high_value_count, distinct_types
        )

        result.update({
            "judge_verdict": verdict,
            "confidence_score": confidence,
            "judge_reasoning": reasoning,
            "scam_detected": verdict in {"GUILTY", "SUSPICIOUS"},
            "engagement_complete": True,
            "extraction_complete": True
        })

    return result


# =============================================================================
# HARDENED VERDICT (CORE LOGIC PRESERVED)
# =============================================================================

def _determine_verdict(state: Dict,
                       entities: Dict,
                       high_value: int,
                       distinct_types: int) -> Tuple[str, float, str]:

    scam_detected = state.get("scam_detected", False)
    scam_type = state.get("scam_type", "Unknown")
    indicators = state.get("scam_indicators", []) or []

    if not scam_detected and not indicators and high_value == 0:
        return "INNOCENT", 0.5, "No evidence detected."

    base_confidence = 0.65 if scam_detected else 0.45

    # Diversity bonus (unchanged logic, but guarded)
    diversity_bonus = 0
    if high_value >= 1 and distinct_types > 0:
        diversity_bonus = min(0.2, (distinct_types - 1) * 0.07)

    # Count bonus (unchanged)
    count_bonus = min(0.15, high_value * 0.03)

    # Indicator dampening (anti-spam refinement)
    indicator_bonus = min(0.05, 0.02 * (len(indicators) ** 0.5))

    raw_confidence = base_confidence + diversity_bonus + count_bonus + indicator_bonus
    confidence = max(0.0, min(0.99, raw_confidence))

    if confidence >= 0.8:
        verdict = "GUILTY"
    elif confidence >= 0.6:
        verdict = "SUSPICIOUS"
    else:
        verdict = "INNOCENT"

    if not scam_detected and verdict == "GUILTY":
        verdict = "SUSPICIOUS"
        confidence = min(confidence, 0.79)

    reasoning = (
        f"Hardened Confidence {confidence:.2f} | "
        f"Detection: {scam_detected} ({scam_type}) | "
        f"Yield: {high_value} | "
        f"Diversity: {distinct_types} | "
        f"Indicators: {len(indicators)}"
    )

    return verdict, confidence, reasoning


# =============================================================================
# SAFE FALLBACK
# =============================================================================

def _check_smart_exit(high_value: int, total: int, turns: int, max_turns: int, distinct_types: int) -> Tuple[bool, str]:
    """
    Improved Exit Strategy - Prevents premature exits:
    - Turn 0:    NEVER exit (prevent premature termination)
    - Turn 1-2:  >=4 high-value AND >=2 distinct types (higher threshold)
    - Turn 3-4:  >=3 high-value AND >=2 distinct types
    - Turn 5-6:  >=3 high-value OR (>=2 high-value AND >=2 distinct types)
    - Turn 7-9:  >=2 high-value
    - Turn 10+:  Force exit
    """
    if turns >= 10:
        return True, f"Max turns reached ({turns}). Forced exit."
    
    # NEVER exit on turn 0 - prevent premature termination
    if turns == 0:
        return False, "Turn 0: Continue engagement"
    
    # Higher thresholds for early turns
    elif 1 <= turns <= 2:
        if high_value >= 4 and distinct_types >= 2:
            return True, f"T{turns}: High-quality yield ({high_value} entities, {distinct_types} types)."
    elif 3 <= turns <= 4:
        if high_value >= 3 and distinct_types >= 2:
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


def _build_prompt(state: Dict[str, Any], turns_used: int, max_turns: int, high_value_count: int,
                  bank_list: list, upi_list: list, url_list: list) -> str:
    """Prepare inputs and build the LLM prompt."""
    history = state.get("conversation_history", [])
    recent_history = ""
    for turn in history[-3:]:
        role = "Honeypot" if turn["role"] == "honeypot" else "Scammer"
        recent_history += f"{role}: {turn['message']}\n"

    last_message = state.get("original_message", "")
    if history and history[-1]["role"] == "scammer":
        last_message = history[-1]["message"]

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

    return PLANNER_PROMPT.format(
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


def _safe_fallback() -> Dict[str, Any]:
    return {
        "planner_action": "engage",
        "strategy_hint": "Fallback due to planning error. Continue engagement safely.",
        "current_agent": "planner"
    }
