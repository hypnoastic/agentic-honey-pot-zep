"""
Response Formatter Agent
Formats the final structured JSON response using OpenAI for summary generation.
Includes error handling, retry logic, and safe JSON parsing.
"""

import json
import logging
from typing import Dict, Any
from utils.llm_client import call_llm
from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """Summarize this scam engagement conversation in 2-3 concise sentences.

SCAM TYPE: {scam_type}
CONVERSATION:
{conversation}

EXTRACTED ENTITIES:
- Bank Accounts: {bank_accounts}
- UPI IDs: {upi_ids}
- Phishing URLs: {phishing_urls}

Focus on:
- What type of scam was attempted
- What tactics the scammer used
- What intelligence was gathered

Keep the summary under 150 words. Be factual and professional."""


def response_formatter_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format the final response with all gathered intelligence.
    """
    
    is_scam = state.get("scam_detected", False)
    scam_type = state.get("scam_type")
    confidence = state.get("confidence_score", 0.0)
    entities = state.get("extracted_entities", {
        "bank_accounts": [],
        "upi_ids": [],
        "phishing_urls": []
    })
    
    try:
        # Generate conversation summary using OpenAI
        summary = _generate_summary(state, entities)
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        summary = _fallback_summary(state, entities)
    
    # Build final response
    final_response = {
        "is_scam": is_scam,
        "scam_type": scam_type,
        "confidence_score": confidence,
        "extracted_entities": {
            "bank_accounts": entities.get("bank_accounts", []),
            "upi_ids": entities.get("upi_ids", []),
            "phishing_urls": entities.get("phishing_urls", [])
        },
        "conversation_summary": summary
    }

    # Preserve agent_response for Live Mode
    prior_final = state.get("final_response")
    
    if prior_final and isinstance(prior_final, dict) and "agent_response" in prior_final:
        final_response["agent_response"] = prior_final["agent_response"]
    
    return {
        "conversation_summary": summary,
        "final_response": final_response,
        "current_agent": "end"
    }


def _generate_summary(state: Dict[str, Any], entities: Dict) -> str:
    """Generate a concise conversation summary using OpenAI."""
    is_scam = state.get("scam_detected", False)
    scam_type = state.get("scam_type", "Unknown")
    conversation_history = state.get("conversation_history", [])
    
    # If not a scam, return simple message
    if not is_scam:
        return "Message analyzed and determined to be non-malicious. No scam indicators detected."
    
    # Format conversation for AI
    conv_text = f"Original message: {state.get('original_message', '')}\n\n"
    for turn in conversation_history:
        role = "Honeypot" if turn.get("role") == "honeypot" else "Scammer"
        conv_text += f"{role}: {turn.get('message', '')}\n"
    
    prompt = SUMMARY_PROMPT.format(
        scam_type=scam_type,
        conversation=conv_text[:3000],
        bank_accounts=", ".join(entities.get("bank_accounts", [])) or "None",
        upi_ids=", ".join(entities.get("upi_ids", [])) or "None",
        phishing_urls=", ".join(entities.get("phishing_urls", [])) or "None"
    )
    
    return call_llm(prompt=prompt, system_instruction="You are an expert summarizer.")


def _fallback_summary(state: Dict[str, Any], entities: Dict) -> str:
    """Generate fallback summary when LLM is unavailable."""
    is_scam = state.get("scam_detected", False)
    scam_type = state.get("scam_type", "Unknown")
    conversation_history = state.get("conversation_history", [])
    
    if not is_scam:
        return "Message analyzed and determined to be non-malicious. No scam indicators detected."
    
    parts = [f"Detected {scam_type} scam attempt."]
    
    if conversation_history:
        parts.append(f"Engaged scammer over {len(conversation_history)} conversation turns.")
    
    entity_parts = []
    bank_count = len(entities.get("bank_accounts", []))
    upi_count = len(entities.get("upi_ids", []))
    url_count = len(entities.get("phishing_urls", []))
    
    if bank_count:
        entity_parts.append(f"{bank_count} bank account(s)")
    if upi_count:
        entity_parts.append(f"{upi_count} UPI ID(s)")
    if url_count:
        entity_parts.append(f"{url_count} phishing URL(s)")
    
    if entity_parts:
        parts.append(f"Extracted: {', '.join(entity_parts)}.")
    
    return " ".join(parts)
