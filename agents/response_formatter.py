"""
Response Formatter Agent (Production Optimized)
- Gemini Flash Summary
- Low token usage
- Deterministic
- Safe fallbacks
"""

import json
import logging
from typing import Dict, Any
from utils.llm_client import call_llm
from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


# =========================================================
# SUMMARY PROMPT (STRUCTURED + TOKEN EFFICIENT)
# =========================================================

SUMMARY_PROMPT = """Summarize the scam engagement in 2-3 concise sentences.

SCAM TYPE: {scam_type}

RECENT CONVERSATION:
{conversation}

EXTRACTED INTELLIGENCE:
- Bank Accounts: {bank_accounts}
- UPI IDs: {upi_ids}
- URLs: {phishing_urls}

Focus on:
• Scam tactic
• Social engineering behavior
• What intelligence was captured

Be factual and professional.
"""


# =========================================================
# MAIN AGENT
# =========================================================

def response_formatter_agent(state: Dict[str, Any]) -> Dict[str, Any]:

    is_scam = state.get("scam_detected", False)
    scam_type = state.get("scam_type", "Unknown")
    confidence = float(state.get("confidence_score", 0.0))

    entities = state.get("extracted_entities", {}) or {}

    try:
        summary = _generate_summary(state, entities)
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        summary = _fallback_summary(state, entities)

    final_response = {
        "scam_detected": is_scam,
        "scam_type": scam_type,
        "confidence_score": confidence,
        "extracted_entities": {
            "bank_accounts": entities.get("bank_accounts", []),
            "upi_ids": entities.get("upi_ids", []),
            "phishing_urls": entities.get("phishing_urls", [])
        },
        "behavioral_signals": state.get("behavioral_signals", []),
        "confidence_factors": state.get("confidence_factors", {}),
        "conversation_summary": summary,
        "persona_name": state.get("persona_name"),
        "engagement_count": state.get("engagement_count", 0),
        "reply": (state.get("final_response") or {}).get("agent_response")
    }

    return {
        "conversation_summary": summary,
        "final_response": final_response,
        "current_agent": "end"
    }


# =========================================================
# SUMMARY GENERATION (TOKEN SAFE)
# =========================================================

def _generate_summary(state: Dict[str, Any], entities: Dict) -> str:

    if not state.get("scam_detected", False):
        return "Message analyzed and determined to be non-malicious."

    scam_type = state.get("scam_type", "Unknown")
    conversation_history = state.get("conversation_history", [])

    # ✅ Only last 6 turns (token safe)
    recent_history = conversation_history[-6:]

    conv_lines = []
    for turn in recent_history:
        role = "Honeypot" if turn.get("role") == "honeypot" else "Scammer"
        conv_lines.append(f"{role}: {turn.get('message', '')}")

    conv_text = "\n".join(conv_lines)

    bank_accounts = _flatten_entities(entities.get("bank_accounts", []))
    upi_ids = _flatten_entities(entities.get("upi_ids", []))
    phishing_urls = _flatten_entities(entities.get("phishing_urls", []))

    prompt = SUMMARY_PROMPT.format(
        scam_type=scam_type,
        conversation=conv_text,
        bank_accounts=", ".join(bank_accounts) or "None",
        upi_ids=", ".join(upi_ids) or "None",
        phishing_urls=", ".join(phishing_urls) or "None"
    )

    return call_llm(
        prompt=prompt,
        system_instruction="You are a cybersecurity analyst summarizing scam intelligence.",
        agent_name="summary",  # ✅ Separate model name in .env
        temperature=0.2        # ✅ Deterministic
    )


# =========================================================
# FALLBACK SUMMARY
# =========================================================

def _fallback_summary(state: Dict[str, Any], entities: Dict) -> str:

    scam_type = state.get("scam_type", "Unknown")
    conversation_history = state.get("conversation_history", [])

    if not state.get("scam_detected", False):
        return "Message analyzed and determined to be non-malicious."

    parts = [f"Detected {scam_type} scam attempt."]

    if conversation_history:
        parts.append(f"{len(conversation_history)} conversation turns recorded.")

    bank_count = len(entities.get("bank_accounts", []))
    upi_count = len(entities.get("upi_ids", []))
    url_count = len(entities.get("phishing_urls", []))

    extracted = []
    if bank_count:
        extracted.append(f"{bank_count} bank account(s)")
    if upi_count:
        extracted.append(f"{upi_count} UPI ID(s)")
    if url_count:
        extracted.append(f"{url_count} phishing URL(s)")

    if extracted:
        parts.append("Extracted: " + ", ".join(extracted) + ".")

    return " ".join(parts)


# =========================================================
# HELPER
# =========================================================

def _flatten_entities(entity_list):
    flattened = []
    for e in entity_list:
        if isinstance(e, dict):
            flattened.append(str(e.get("value", "")))
        else:
            flattened.append(str(e))
    return flattened
