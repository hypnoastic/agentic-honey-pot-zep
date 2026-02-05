"""
Planner Agent
"The Mastermind"
Decides the high-level strategy and next action based on the conversation state.
Transitions from linear flow to dynamic routing.
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

DECISION LOGIC:
1. "engage": Keep the conversation going. Ask questions, stall, waste their time.
2. "judge": Conclude the conversation when:
   - We have successfully extracted valuable intelligence (bank accounts, UPI IDs, URLs)
   - Max turns ({max_turns}) reached
   - Scammer has stopped responding or ended conversation
   - Diminishing returns (scammer is repeating themselves with no new info)
3. "end": ONLY if it is clearly NOT a scam.

SMART EXIT CRITERIA:
- If extracted_count > 0 AND the scammer is just repeating threats without new information, choose "judge"
- If extracted_count >= 2, consider "judge" to avoid over-engagement
- Balance: Maximize extraction while minimizing wasted turns

STRATEGY GUIDELINES:
- If they ask for money, feign ignorance or technical issues.
- If they threaten action (police/block), act scared but incompetent.
- ADAPT: If a "Winning Tactic" is suggested above, TRY TO INCORPORATE IT.

Respond with JSON ONLY:
{{
    "action": "engage" | "judge" | "end",
    "strategy_hint": "Brief guidance for the persona..."
}}"""

def planner_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decide the next action and strategy.
    Uses LLM to make strategic decisions from the FIRST turn.
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

    entities = state.get("extracted_entities", {})
    entity_count = len(entities.get("bank_accounts", [])) + len(entities.get("upi_ids", [])) + len(entities.get("phishing_urls", []))
    
    max_turns = state.get("max_engagements", 8)
    turns_used = state.get("engagement_count", 0)

    # Log turn info
    logger.info(f"Planner: Turn {turns_used}/{max_turns}, Entities extracted: {entity_count}")

    # NOTE: Removed "Smart Quit" logic - LLM now decides on every turn
    # The planner should make strategic decisions, not hardcoded rules

    # ROI Check (still useful for cost optimization on repeated patterns)
    scam_stats = state.get("scam_stats", {})
    success_rate = scam_stats.get("success_rate", 0.5)
    total_attempts = scam_stats.get("total_attempts", 0)
    
    # If we have significant data (>10) and success is terrible (<5%)
    # SKIP ENGAGEMENT to save cost. (More conservative threshold)
    if total_attempts > 10 and success_rate < 0.05:
        logger.info(f"ROI Decision: VERY LOW SUCCESS RATE ({success_rate:.2f}). Skipping engagement.")
        
        from utils.logger import AgentLogger
        AgentLogger.plan_decision(
            current_turn=turns_used,
            max_turns=max_turns,
            decision="judge",
            reasoning=f"ROI PRUNE: Success rate {success_rate:.2f} is too low."
        )
        return {
            "planner_action": "judge",
            "strategy_hint": "Skipping engagement due to historically very low success rate.",
            "current_agent": "planner"
        }


    winning_tactics = state.get("winning_strategies", [])
    if winning_tactics:
        tactics_str = "- " + "\n- ".join(winning_tactics)
    else:
        tactics_str = "No specific past tactics available."

    failures = state.get("past_failures", [])
    if failures:
        failures_str = "- " + "\n- ".join(failures)
    else:
        failures_str = "No specific failed patterns to avoid."

    # Temporal Pacing Logic
    temporal = state.get("temporal_stats", {})
    avg_turns = temporal.get("avg_turns", 4.0)
    sample_size = temporal.get("sample_size", 0)
    
    if sample_size > 2:
        if turns_used < avg_turns - 1:
            pacing_info = f"AVG SUCCESS AT TURN {avg_turns}. Currently Turn {turns_used}. ADVICE: STALL. DO NOT EXTRACT YET."
        elif turns_used >= avg_turns:
            pacing_info = f"AVG SUCCESS AT TURN {avg_turns}. Currently Turn {turns_used}. ADVICE: GOOD TIME TO EXTRACT."
        else:
            pacing_info = f"Approaching optimal extraction turn ({avg_turns}). Prepared to pivot."
    else:
        pacing_info = "No historical pacing data available. Use best judgement."

    prompt = PLANNER_PROMPT.format(
        scam_detected=state.get("is_scam", False),
        scam_type=state.get("scam_type", "Unknown"),
        turns_used=turns_used,
        max_turns=max_turns,
        extracted_count=entity_count,
        temporal_pacing_info=pacing_info,
        familiarity_score=state.get("familiarity_score", 0.0),
        recent_history=recent_history,
        winning_strategies=tactics_str,
        past_failures=failures_str,
        latest_message=last_message
    )

    try:
        # Call OpenAI via Utils
        response_text = call_llm(
            prompt=prompt,
            system_instruction="You are a strategic AI planner for a scambaiting system.",
            json_mode=True
        )
        
        # Parse JSON
        plan = json.loads(response_text)
        action = plan.get("action", "judge")
        hint = plan.get("strategy_hint", "Continue engagement")
        
        # Internal Explainability (Trace)
        trace_id = f"trace_{turns_used}_{scam_stats.get('total_attempts', 0)}"
        logger.info(f"PLANNER TRACE [{trace_id}]: Selected {action} based on {len(winning_tactics)} winning strategies and {len(failures)} failures.")
        
        # Transparent Logging
        from utils.logger import AgentLogger
        AgentLogger.plan_decision(
            current_turn=turns_used,
            max_turns=max_turns,
            decision=action,
            reasoning=hint
        )
        
        return {
            "planner_action": action,
            "strategy_hint": hint,
            "current_agent": "planner" # will serve as routing node
        }

    except Exception as e:
        logger.error(f"Planner failed: {e}")
        # Fallback safe defaults
        return {
            "planner_action": "judge",
            "strategy_hint": "Error in planning, finish up.",
            "error": str(e)
        }
