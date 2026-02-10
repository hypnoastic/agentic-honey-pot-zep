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

PLANNER_PROMPT = """You are the STRATEGIC PLANNER for an AI Honey-Pot system.
Your goal is to waste the scammer's time (scambaiting) and extract intelligence (bank accounts, UPIs, phishing URLs).

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
1. "engage": Keep the conversation going. Ask questions, stall, waste their time.
2. "judge": Conclude the conversation when:
   - We have successfully extracted valuable intelligence (bank accounts, UPI IDs, URLs)
   - Max turns ({max_turns}) reached
   - Scammer has stopped responding or ended conversation
   - Diminishing returns (scammer is repeating themselves with no new info)
3. "end": ONLY if it is clearly NOT a scam.

WHEN action="judge", YOU MUST ALSO PROVIDE:
- verdict: "GUILTY" (confirmed scam), "INNOCENT" (not a scam), or "SUSPICIOUS" (likely scam but inconclusive)
- confidence_score: 0.0-1.0
- reasoning: Brief explanation of your verdict

SMART EXIT CRITERIA:
- If extracted_count > 0 AND the scammer is just repeating threats without new information, choose "judge"
- If extracted_count >= 2, consider "judge" to avoid over-engagement
- Balance: Maximize extraction while minimizing wasted turns

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
    
    # Prepare inputs
    history = state.get("conversation_history", [])
    recent_history = ""
    for turn in history[-3:]:
        role = "Honeypot" if turn["role"] == "honeypot" else "Scammer"
        recent_history += f"{role}: {turn['message']}\n"

    last_message = state.get("original_message", "")
    if history and history[-1]["role"] == "scammer":
        last_message = history[-1]["message"]

    # READ entities from state (set by Intelligence Extraction or Pre-filter)
    entities = state.get("extracted_entities", {})
    
    # Flatten entity lists for counting
    bank_accounts = entities.get("bank_accounts", [])
    upi_ids = entities.get("upi_ids", [])
    phishing_urls = entities.get("phishing_urls", [])
    phone_numbers = entities.get("phone_numbers", [])
    
    # Handle both dict format and string format
    bank_list = [e.get("value", e) if isinstance(e, dict) else e for e in bank_accounts]
    upi_list = [e.get("value", e) if isinstance(e, dict) else e for e in upi_ids]
    url_list = [e.get("value", e) if isinstance(e, dict) else e for e in phishing_urls]
    phone_list = [e.get("value", e) if isinstance(e, dict) else e for e in phone_numbers]
    
    # High-value entities for decision making
    high_value_count = len(bank_list) + len(upi_list) + len(url_list)
    total_entities = high_value_count + len(phone_list)
    
    from config import get_settings
    settings = get_settings()
    max_turns = state.get("max_engagements", settings.max_engagement_turns)
    turns_used = state.get("engagement_count", 0)

    logger.info(f"Planner: Turn {turns_used}/{max_turns}, High-value entities: {high_value_count}, Total: {total_entities}")

    # =========================================================================
    # SMART EXIT: Heuristic-based completion check
    # Uses entity counts from state (set by Intelligence Extraction)
    # =========================================================================
    should_complete, completion_reason = _check_smart_exit(
        high_value_count, total_entities, turns_used, max_turns
    )
    
    if should_complete:
        logger.info(f"SMART COMPLETION: {completion_reason}")
        
        # Determine verdict based on evidence
        verdict, confidence, reasoning = _determine_verdict(
            state, entities, high_value_count
        )
        
        from utils.logger import AgentLogger
        AgentLogger.plan_decision(
            current_turn=turns_used,
            max_turns=max_turns,
            decision="judge",
            reasoning=f"SMART EXIT: {completion_reason}"
        )
        
        return {
            "planner_action": "judge",
            "strategy_hint": completion_reason,
            "judge_verdict": verdict,
            "confidence_score": confidence,
            "judge_reasoning": reasoning,
            "scam_detected": verdict in ["GUILTY", "SUSPICIOUS"],
            "engagement_complete": True,
            "extraction_complete": True
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


def _check_smart_exit(high_value: int, total: int, turns: int, max_turns: int) -> tuple:
    """
    Deterministic exit decision based on entity counts and turn limits.
    Uses counts from state (set by Intelligence Extraction), NOT inline scanning.
    """
    if high_value >= 5:
        return True, f"Extracted {high_value} high-value entities. Excellent."
    if high_value >= 4 and turns >= 7:
        return True, f"Extracted {high_value} entities after {turns} turns. Great."
    if high_value >= 3 and turns >= 8:
        return True, f"Extracted {high_value} entities after {turns} turns. Good."
    if high_value >= 2 and turns >= 8:
        return True, f"Extracted {high_value} entities after {turns} turns. Good."
    if high_value >= 1 and turns >= 10:
        return True, f"Extracted {high_value} entity after {turns} turns. Sufficient."
    if total >= 4 and turns >= 6:
        return True, f"Extracted {total} total entities after {turns} turns."
    if total >= 1 and turns >= int(max_turns * 0.7):
        return True, f"{turns} turns (70%+ max). Have {total} entities."
    if turns >= max_turns - 1:
        return True, f"Approaching max turns ({turns}/{max_turns})."
    
    return False, ""


def _determine_verdict(state: Dict, entities: Dict, entity_count: int) -> tuple:
    """
    Deterministic verdict based on evidence in state.
    LLM can override if it reaches action=judge.
    """
    scam_detected = state.get("scam_detected", False)
    scam_type = state.get("scam_type")
    indicators = state.get("scam_indicators", [])
    
    if scam_detected and entity_count >= 2:
        return "GUILTY", 0.9, f"Confirmed {scam_type} scam with {entity_count} entities extracted."
    elif scam_detected and entity_count >= 1:
        return "GUILTY", 0.8, f"Confirmed {scam_type} with evidence."
    elif scam_detected:
        return "SUSPICIOUS", 0.7, f"Likely {scam_type} but limited entity extraction."
    elif len(indicators) > 0:
        return "SUSPICIOUS", 0.6, f"Found {len(indicators)} indicators but not confirmed."
    else:
        return "INNOCENT", 0.5, "No clear evidence of scam activity."
