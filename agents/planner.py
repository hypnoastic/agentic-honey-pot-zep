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
Your goal is to waste the scammer's time (scambaiting) and extract intelligence (bank accounts, UPIs).

CURRENT STATE:
- Scam Detected: {scam_detected}
- Scam Type: {scam_type}
- Turns Used: {turns_used}/{max_turns}
- Extracted Entities: {extracted_count}

CONVERSATION HISTORY (Last 3 turns):
{recent_history}

LATEST SCAMMER MESSAGE:
"{latest_message}"

DECISION LOGIC:
1. "engage": DEFAULT ACTION. If the scammer is still talking, KEEP TALKING. Waste their time. Ask dumb questions.
2. "judge": ONLY if we have hit max turns ({max_turns}) OR the user has stopped responding/said goodbye.
3. "end": ONLY if it is clearly NOT a scam.

STRATEGY GUIDELINES:
- If they ask for money, feign ignorance or technical issues.
- If they threaten action (police/block), act scared but incompetent.
- DO NOT JUDGE EARLY. We want to maximize the conversation duration.

Respond with JSON ONLY:
{{
    "action": "engage" | "judge" | "end",
    "strategy_hint": "Brief guidance for the persona..."
}}"""

def planner_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decide the next action and strategy.
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
    
    max_turns = state.get("max_engagements", 5)
    turns_used = state.get("engagement_count", 0)

    prompt = PLANNER_PROMPT.format(
        scam_detected=state.get("is_scam", False),
        scam_type=state.get("scam_type", "Unknown"),
        turns_used=turns_used,
        max_turns=max_turns,
        extracted_count=entity_count,
        recent_history=recent_history,
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
