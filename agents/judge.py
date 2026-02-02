"""
Agentic Judge
"The Supreme Court"
Replaces math-based scoring with an LLM that acts as a Judge to evaluate the case.
Produces a Verdict and a Reasoning.
"""

import json
import logging
from typing import Dict, Any
from utils.llm_client import call_llm

logger = logging.getLogger(__name__)

JUDGE_PROMPT = """You are the AGENTIC JUDGE for a Cyber-Crime Investigation unit.
Your job is to review the evidence collected by the Honey-Pot and issue a Verdict.

EVIDENCE DOSSIER:
- Original Message: "{original_message}"
- Suspected Scam Type: {scam_type}
- Extracted Bank Accounts: {bank_accounts}
- Extracted UPI IDs: {upi_ids}
- Extracted URLs: {phishing_urls}
- Scam Indicators Found: {indicators}

CONVERSATION TRANSCRIPT:
{transcript}

TASK:
1. Analyze the evidence. Is this definitively a scam?
2. Assign a Confidence Score (0.00 to 1.00).
3. Write a "Verdict" (GUILTY / INNOCENT / SUSPICIOUS).
4. Write a "Reasoning" explaining your decision.

Respond with JSON ONLY:
{{
    "verdict": "GUILTY" | "INNOCENT" | "SUSPICIOUS",
    "confidence_score": 0.95,
    "reasoning": "The user explicitly asked for money..."
}}"""

def agentic_judge_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate the session and produce a verdict.
    """
    logger.info("Agentic Judge: Deliberating...")

    # Prepare Transcript
    history = state.get("conversation_history", [])
    transcript = ""
    for turn in history:
        role = "Honeypot" if turn["role"] == "honeypot" else "Scammer"
        transcript += f"{role}: {turn['message']}\n"

    entities = state.get("extracted_entities", {})
    
    prompt = JUDGE_PROMPT.format(
        original_message=state.get("original_message", ""),
        scam_type=state.get("scam_type", "Unknown"),
        bank_accounts=entities.get("bank_accounts", []),
        upi_ids=entities.get("upi_ids", []),
        phishing_urls=entities.get("phishing_urls", []),
        indicators=state.get("scam_indicators", []),
        transcript=transcript[:5000] # Cap length
    )

    try:
        # Call OpenAI via Utils
        response_text = call_llm(
            prompt=prompt,
            system_instruction="You are an expert AI Judge evaluating scam attempts.",
            json_mode=True
        )
        
        result = json.loads(response_text)
        is_scam_final = result.get("is_guilty", False) # Assuming 'is_guilty' might be a new key or derived from 'verdict'
        confidence = result.get("confidence_score", 0.0)
        
        # Transparent Logging
        from utils.logger import AgentLogger
        AgentLogger.verdict(is_scam_final, confidence, result.get("reasoning", ""))
        
        return {
            "is_scam": is_scam_final,
            "judge_verdict": result.get("verdict", "SUSPICIOUS"), # Using 'result' instead of 'verdict_data'
            "confidence_score": float(result.get("confidence_score", 0.0)),
            "judge_reasoning": result.get("reasoning", "No reasoning provided."),
            "current_agent": "response_formatter"
        }

    except Exception as e:
        logger.error(f"Judge failed: {e}")
        return {
            "judge_verdict": "ERROR",
            "confidence_score": 0.0,
            "judge_reasoning": f"Judge error: {e}"
        }
