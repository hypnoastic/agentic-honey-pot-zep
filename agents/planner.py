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
    
    from config import get_settings
    settings = get_settings()
    max_turns = state.get("max_engagements", settings.max_engagement_turns)
    turns_used = state.get("engagement_count", 0)

    # Log turn info
    logger.info(f"Planner: Turn {turns_used}/{max_turns}, Entities extracted: {entity_count}")

    # =========================================================================
    # INLINE ENTITY SCANNING: Detect entities from conversation history
    # This helps when entities aren't persisted across API calls
    # =========================================================================
    import re
    
    # UPI ID pattern: xxx@upi, xxx@paytm, xxx@ybl, xxx@gpay, etc.
    upi_pattern = r'\b[a-zA-Z0-9._-]+@[a-zA-Z]+\b'
    # Phone number pattern: 10 digits starting with 7/8/9 (with optional +91 prefix)
    # Negative lookbehind prevents matching within longer numbers (like bank accounts)
    phone_pattern = r'(?<!\d)(?:\+91)?[789]\d{9}(?!\d)'
    # Bank account pattern: 9-18 digit numbers
    bank_pattern = r'\b\d{11,18}\b'
    # Phishing URL pattern: http/https links with suspicious domains
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    
    scanned_upis = set()
    scanned_phones = set()
    scanned_banks = set()
    scanned_urls = set()
    
    for turn in history:
        text = turn.get("message", "")
        # Find UPI IDs (exclude email-like patterns)
        upis = [u for u in re.findall(upi_pattern, text) if not u.endswith('@gmail') and not u.endswith('@email')]
        scanned_upis.update(upis)
        # Find phone numbers in scammer messages
        if turn.get("role") == "scammer":
            phones = re.findall(phone_pattern, text)
            scanned_phones.update(phones)
            # Find bank accounts (long digit strings)
            banks = re.findall(bank_pattern, text)
            scanned_banks.update(banks)
            # Find URLs
            urls = re.findall(url_pattern, text)
            scanned_urls.update(urls)
    
    # Also scan the original message
    scanned_upis.update([u for u in re.findall(upi_pattern, last_message) if not u.endswith('@gmail')])
    scanned_phones.update(re.findall(phone_pattern, last_message))
    scanned_banks.update(re.findall(bank_pattern, last_message))
    scanned_urls.update(re.findall(url_pattern, last_message))
    
    # Add to entity count
    scanned_entity_count = len(scanned_upis) + len(scanned_phones) + len(scanned_banks) + len(scanned_urls)
    if scanned_entity_count > entity_count:
        logger.info(f"Planner: Inline scan found {len(scanned_upis)} UPIs, {len(scanned_phones)} phones, {len(scanned_banks)} banks, {len(scanned_urls)} URLs")
        entity_count = scanned_entity_count
        # Update entities dict for smart completion logic
        entities = {
            "upi_ids": list(scanned_upis),
            "phone_numbers": list(scanned_phones),
            "bank_accounts": list(scanned_banks),
            "phishing_urls": list(scanned_urls)
        }


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

    # =========================================================================
    # SMART COMPLETION LOGIC: Decide if we have enough valuable intelligence
    # =========================================================================
    
    # Count valuable entities (UPI IDs, Bank Accounts, and URLs are high value)
    bank_accounts = entities.get("bank_accounts", [])
    upi_ids = entities.get("upi_ids", [])
    phishing_urls = entities.get("phishing_urls", [])
    phone_numbers = entities.get("phone_numbers", [])
    
    # URLs are also high-value - they're direct evidence of phishing
    high_value_count = len(bank_accounts) + len(upi_ids) + len(phishing_urls)
    total_entities = high_value_count + len(phone_numbers)
    
    # SMART EXIT CONDITIONS (adjusted for max_turns=15):
    # 1. If we have 5+ high-value entities → exit immediately (excellent extraction)
    # 2. If we have 4+ high-value entities AND 7+ turns → exit (great extraction)
    # 3. If we have 3+ high-value entities AND 8+ turns → exit (good extraction)
    # 4. If we have 2+ high-value entities AND 8+ turns → exit (good extraction)
    # 5. If we have 1+ high-value entity AND 10+ turns → exit (decent extraction)
    # 6. If we're at 70%+ of max turns with ANY entity → exit
    # 7. Approaching max turns → must exit
    
    should_complete = False
    completion_reason = ""
    
    if high_value_count >= 5:
        should_complete = True
        completion_reason = f"Extracted {high_value_count} high-value entities (UPI/Bank/URL). Excellent extraction."
    elif high_value_count >= 4 and turns_used >= 7:
        should_complete = True
        completion_reason = f"Extracted {high_value_count} high-value entities after {turns_used} turns. Great extraction."
    elif high_value_count >= 3 and turns_used >= 8:
        should_complete = True
        completion_reason = f"Extracted {high_value_count} high-value entities after {turns_used} turns. Good extraction."
    elif high_value_count >= 2 and turns_used >= 8:
        should_complete = True
        completion_reason = f"Extracted {high_value_count} high-value entities after {turns_used} turns. Good extraction."
    elif high_value_count >= 1 and turns_used >= 10:
        should_complete = True
        completion_reason = f"Extracted {high_value_count} entity after {turns_used} turns. Sufficient extraction."
    elif total_entities >= 4 and turns_used >= 6:
        # If we have 4+ total entities (including phones), also good to exit
        should_complete = True
        completion_reason = f"Extracted {total_entities} total entities after {turns_used} turns. Good extraction."
    elif total_entities >= 1 and turns_used >= (max_turns * 0.7):
        should_complete = True
        completion_reason = f"{turns_used} turns used (70%+ of max). Have {total_entities} entities. Time to complete."
    elif turns_used >= max_turns - 1:
        should_complete = True
        completion_reason = f"Approaching max turns ({turns_used}/{max_turns}). Completing engagement."
    
    if should_complete:
        logger.info(f"SMART COMPLETION: {completion_reason}")
        
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
            "current_agent": "planner",
            "extraction_complete": True,  # Signal that extraction is done
            "extracted_entities": {
                "bank_accounts": entities.get("bank_accounts", []),
                "upi_ids": entities.get("upi_ids", []),
                "phishing_urls": entities.get("phishing_urls", []),
                "phone_numbers": entities.get("phone_numbers", [])
            }
        }
    
    # =========================================================================
    # If no smart exit triggered, proceed to LLM-based strategic planning
    # =========================================================================


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
