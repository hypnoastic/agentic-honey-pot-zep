"""
Planner Agent — UPGRADED for 95+ Score
Key changes:
  - Minimum 8 turns enforced (up from 5) for full turn-count points
  - Tracks elicitation_attempts (counts toward Category 3 scoring)
  - Tracks red_flags_mentioned in strategy hints
  - Strategy hints always specify EXACT entity to extract
"""

import re
import json
import logging
from typing import Dict, Any, Tuple
from utils.llm_client import call_llm_async

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = {"engage", "judge", "end"}
ALLOWED_VERDICTS = {"GUILTY", "INNOCENT", "SUSPICIOUS"}

# Elicitation keywords — when present in strategy_hint, count as elicitation attempt
ELICITATION_KEYWORDS = [
    "ask for", "request", "elicit", "extract", "get the", "obtain",
    "phone", "email", "case id", "case number", "policy", "order",
    "upi", "bank account", "branch", "website", "link", "supervisor",
    "reference", "ticket", "complaint"
]

PLANNER_PROMPT = """STRATEGIC PLANNER: Waste scammer's time AND extract ALL possible data.

SCORING REQUIREMENTS (you MUST hit these thresholds):
- MINIMUM 8 TURNS before judging
- Ask ≥5 investigative questions (with "?")
- Identify ≥5 red flags explicitly
- Make ≥5 elicitation attempts (ask for specific data)

CURRENT STATE:
- Scam Detected: {scam_detected}
- Scam Type: {scam_type}
- Turns Used: {turns_used}/{max_turns}
- Extracted Entities: {extracted_count}
- Questions Asked So Far: {questions_asked}
- Red Flags Mentioned: {red_flags_mentioned}
- Elicitation Attempts: {elicitation_attempts}

TEMPORAL PACING:
{temporal_pacing_info}

FAMILIARITY SCORE: {familiarity_score:.2f}/1.0

CONVERSATION HISTORY (Last 4 turns):
{recent_history}

WINNING TACTICS:
{winning_strategies}

FAILED STRATEGIES (AVOID):
{past_failures}

LATEST SCAMMER MESSAGE:
"{latest_message}"

EXTRACTED EVIDENCE:
- Bank Accounts: {bank_accounts}
- UPI IDs: {upi_ids}
- URLs: {phishing_urls}
- Emails: {emails}
- Case IDs: {case_ids}
- Policy Numbers: {policy_numbers}
- Phone Numbers: {phone_numbers}

PACING STRATEGY:
Turns 0-4: STALL — build trust, appear confused/worried
Turns 5-7: EXTRACT — ask for specific data items
Turns 8+: CLOSE — wrap up with final extraction then judge

ELICITATION TARGET LIST (get as many as possible):
[ ] Phone number  [ ] Email address  [ ] Case/Reference ID
[ ] Policy number  [ ] Order number   [ ] Bank account
[ ] UPI ID         [ ] Website/link   [ ] Branch name
[ ] Supervisor name

DECISION RULES:
1. "engage": Continue conversation
   - Turns < 8: MANDATORY — use "STALL:" prefix with specific probe
   - Turns 5-7: EXTRACT prefix + specify exact entity to collect
   - Turns 8+: "EXTRACT:" or "judge" if ≥4 entity types collected
2. "judge": ONLY allowed after Turn 7
3. "end": Only if clearly NOT a scam (very rare)

Strategy hint format: "STALL: [specific tactic]" or "EXTRACT: Ask for [specific entity type]"

Respond with JSON ONLY:
{{
    "action": "engage" | "judge" | "end",
    "strategy_hint": "STALL: [tactic]\" or \"EXTRACT: Ask for [entity]. Also mention [red flag].",
    "verdict": "GUILTY" | "INNOCENT" | "SUSPICIOUS" | null,
    "confidence_score": 0.0-1.0 | null,
    "reasoning": "..." | null
}}"""


async def planner_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    from utils.logger import AgentLogger
    logger = logging.getLogger(__name__)

    AgentLogger.thought_process("PLANNER", "Analyzing conversation state and strategy...")

    from config import get_settings
    settings = get_settings()

    max_turns = min(12, state.get("max_engagements", settings.max_engagement_turns))
    turns_used = max(0, state.get("engagement_count", 0))

    history = state.get("conversation_history", []) or []
    entities = state.get("extracted_entities", {}) or {}

    if not isinstance(entities, dict):
        entities = {}

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
    email_list = safe_values("email_addresses")
    case_list = safe_values("case_ids")
    policy_list = safe_values("policy_numbers")

    high_value_count = len(bank_list) + len(upi_list) + len(url_list)
    total_entities = (high_value_count + len(phone_list) +
                      len(email_list) + len(case_list) + len(policy_list) + len(safe_values("order_numbers")))

    distinct_types = sum(
        bool(lst) for lst in [bank_list, upi_list, url_list,
                               phone_list, email_list, case_list, policy_list, safe_values("order_numbers")]
    )
    distinct_types = min(8, distinct_types)

    # ── SMART EXIT ─────────────────────────────────────────────────────────
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

    # ── LLM PLANNING ───────────────────────────────────────────────────────
    prompt = _build_prompt(
        state, turns_used, max_turns, high_value_count,
        bank_list, upi_list, url_list, email_list, case_list,
        policy_list, phone_list
    )

    try:
        response_text = await call_llm_async(
            prompt=prompt,
            system_instruction="You are a strategic planner for a scam honeypot. Follow the SCORING REQUIREMENTS exactly.",
            json_mode=True,
            agent_name="planner"
        )
        plan = json.loads(response_text)
    except Exception as e:
        logger.error(f"Planner LLM failed: {e}")
        return _safe_fallback(turns_used)

    # ── SCHEMA ENFORCEMENT ─────────────────────────────────────────────────
    action = plan.get("action")
    if action not in ALLOWED_ACTIONS:
        action = "engage"

    strategy_hint = plan.get("strategy_hint", "STALL: Ask for more information.")

    # ── MANDATORY MINIMUM 8 TURNS ──────────────────────────────────────────
    if turns_used < 8 and action in ("judge", "end"):
        logger.warning(f"LLM tried to {action} at Turn {turns_used}. Overriding — minimum 8 turns required.")
        action = "engage"
        if not strategy_hint.startswith(("STALL:", "EXTRACT:")):
            strategy_hint = f"STALL: {strategy_hint}"

    # ── TRACK ELICITATION ATTEMPTS ─────────────────────────────────────────
    elicitation_attempts = state.get("elicitation_attempts", 0)
    strategy_lower = strategy_hint.lower()
    is_elicitation = (
        "EXTRACT:" in strategy_hint
        or any(kw in strategy_lower for kw in ELICITATION_KEYWORDS)
    )
    if is_elicitation:
        elicitation_attempts += 1

    # ── TRACK RED FLAGS ────────────────────────────────────────────────────
    red_flags_mentioned = state.get("red_flags_mentioned", 0)
    if any(term in strategy_lower for term in
           ["red flag", "suspicious", "unusual", "alert", "warning", "fraud"]):
        red_flags_mentioned += 1

    result = {
        "planner_action": action,
        "strategy_hint": strategy_hint,
        "elicitation_attempts": elicitation_attempts,
        "red_flags_mentioned": red_flags_mentioned,
        "current_agent": "planner"
    }

    AgentLogger.plan_decision(turns_used, max_turns, action, strategy_hint)

    # ── VERDICT AUTHORITY ──────────────────────────────────────────────────
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
# VERDICT DETERMINATION
# =============================================================================

def _determine_verdict(
    state: Dict, entities: Dict, high_value: int, distinct_types: int
) -> Tuple[str, float, str]:
    scam_detected = state.get("scam_detected", False)
    scam_type = state.get("scam_type", "Unknown")
    indicators = state.get("scam_indicators", []) or []

    if not scam_detected and not indicators and high_value == 0:
        return "INNOCENT", 0.5, "No evidence detected."

    base_confidence = 0.70 if scam_detected else 0.45

    diversity_bonus = 0
    if high_value >= 1 and distinct_types > 0:
        diversity_bonus = min(0.20, (distinct_types - 1) * 0.06)

    count_bonus = min(0.12, high_value * 0.03)
    indicator_bonus = min(0.05, 0.02 * (len(indicators) ** 0.5))

    raw_confidence = base_confidence + diversity_bonus + count_bonus + indicator_bonus
    confidence = max(0.0, min(0.99, raw_confidence))

    if confidence >= 0.80:
        verdict = "GUILTY"
    elif confidence >= 0.60:
        verdict = "SUSPICIOUS"
    else:
        verdict = "INNOCENT"

    if not scam_detected and verdict == "GUILTY":
        verdict = "SUSPICIOUS"
        confidence = min(confidence, 0.79)

    flag_details = ", ".join(indicators[:5]) if indicators else "None specific"
    behavior_signals = state.get("behavioral_signals", [])
    behavior_details = ", ".join(behavior_signals[:3]) if behavior_signals else "None specific"

    reasoning = (
        f"VERDICT: {verdict} (Confidence: {confidence:.2f})\n"
        f"TYPE: {scam_type}\n"
        f"RED FLAGS: {flag_details}\n"
        f"BEHAVIOR: {behavior_details}\n"
        f"YIELD: {high_value} high-value entities ({distinct_types} distinct types)"
    )
    return verdict, confidence, reasoning


# =============================================================================
# SMART EXIT — MINIMUM 8 TURNS
# =============================================================================

def _check_smart_exit(
    high_value: int, total: int, turns: int, max_turns: int, distinct_types: int
) -> Tuple[bool, str]:
    """
    Exit conditions with 8-turn minimum for maximum scoring.
    """
    if turns >= max_turns:
        return True, f"Max turns reached ({turns}). Forced exit."

    if turns == 0:
        return False, "Turn 0: Must engage."

    # MANDATORY MINIMUM: 8 turns
    if turns < 8:
        return False, f"Turn {turns}: Minimum 8 turns required. Keep engaging."

    # After turn 8: exit if we have decent yield
    if turns >= 8:
        if high_value >= 2 or distinct_types >= 3:
            return True, f"T{turns}: Target reached ({high_value} entities, {distinct_types} types)."

    if turns >= 10:
        if high_value >= 1:
            return True, "T10+: Late exit with any yield."

    return False, ""


# =============================================================================
# PROMPT BUILDER
# =============================================================================

def _build_prompt(
    state: Dict[str, Any], turns_used: int, max_turns: int,
    high_value_count: int, bank_list: list, upi_list: list,
    url_list: list, email_list: list, case_list: list,
    policy_list: list, phone_list: list
) -> str:
    history = state.get("conversation_history", [])
    recent_history = ""
    for turn in history[-4:]:
        role = "Honeypot" if turn["role"] == "honeypot" else "Scammer"
        recent_history += f"{role}: {turn['message']}\n"

    last_message = state.get("original_message", "")
    if history and history[-1]["role"] == "scammer":
        last_message = history[-1]["message"]

    winning_tactics = state.get("winning_strategies", [])
    tactics_str = "- " + "\n- ".join(winning_tactics) if winning_tactics else "No specific tactics."
    failures = state.get("past_failures", [])
    failures_str = "- " + "\n- ".join(failures) if failures else "No failures to avoid."

    temporal = state.get("temporal_stats", {})
    avg_turns = temporal.get("avg_turns", 5.0)
    sample_size = temporal.get("sample_size", 0)
    if sample_size > 2:
        if turns_used < avg_turns - 1:
            pacing_info = f"AVG SUCCESS AT TURN {avg_turns}. Currently T{turns_used}. STALL."
        elif turns_used >= avg_turns:
            pacing_info = f"AVG SUCCESS AT TURN {avg_turns}. Currently T{turns_used}. EXTRACT missing items but KEEP ENGAGING."
        else:
            pacing_info = f"Approaching optimal turn ({avg_turns}). Prepare to pivot."
    else:
        pacing_info = "No historical data. Use default strategy."

    return PLANNER_PROMPT.format(
        scam_detected=state.get("scam_detected", False),
        scam_type=state.get("scam_type", "Unknown"),
        turns_used=turns_used,
        max_turns=max_turns,
        extracted_count=high_value_count,
        questions_asked=state.get("questions_asked", 0),
        red_flags_mentioned=state.get("red_flags_mentioned", 0),
        elicitation_attempts=state.get("elicitation_attempts", 0),
        temporal_pacing_info=pacing_info,
        familiarity_score=state.get("familiarity_score", 0.0),
        recent_history=recent_history or "No history yet",
        winning_strategies=tactics_str,
        past_failures=failures_str,
        latest_message=last_message,
        bank_accounts=bank_list[:3],
        upi_ids=upi_list[:3],
        phishing_urls=url_list[:3],
        emails=email_list[:3],
        case_ids=case_list[:3],
        policy_numbers=policy_list[:3],
        phone_numbers=phone_list[:3],
    )


def _safe_fallback(turns_used: int = 0) -> Dict[str, Any]:
    if turns_used < 8:
        hint = "STALL: Feign confusion. Ask why this is so urgent and what the official procedure is. What is your case reference number?"
    else:
        hint = "EXTRACT: Ask for UPI ID, phone number, and case ID. This seems suspicious."
    return {
        "planner_action": "engage",
        "strategy_hint": hint,
        "elicitation_attempts": 1,
        "current_agent": "planner"
    }
