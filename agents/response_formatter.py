"""
Response Formatter Agent
Formats the final structured JSON response using Gemini for summary generation.
Includes error handling, retry logic, and safe JSON parsing.
"""

import json
import time
import logging
from typing import Dict, Any, Optional
from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Initialize Gemini client
_client = None

def _get_gemini_client():
    """Get or create Gemini client."""
    global _client
    if _client is None and settings.google_api_key:
        from google import genai
        _client = genai.Client(api_key=settings.google_api_key)
    return _client


def _call_gemini_with_retry(client, prompt: str, max_retries: int = None) -> Optional[str]:
    """Call Gemini API with exponential backoff retry."""
    max_retries = max_retries or settings.api_retry_attempts
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                wait_time = (2 ** attempt) + 1
                logger.warning(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                logger.error(f"Gemini API error: {e}")
                raise
    
    raise RuntimeError(f"Failed after {max_retries} retry attempts")


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
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with final formatted response
    """
    client = _get_gemini_client()
    if not client:
        raise RuntimeError("Gemini API client not initialized. Please set GOOGLE_API_KEY in .env")
    
    is_scam = state.get("scam_detected", False)
    scam_type = state.get("scam_type")
    confidence = state.get("confidence_score", 0.0)
    entities = state.get("extracted_entities", {
        "bank_accounts": [],
        "upi_ids": [],
        "phishing_urls": []
    })
    
    try:
        # Generate conversation summary using Gemini
        summary = _generate_summary(client, state, entities)
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
    
    return {
        "conversation_summary": summary,
        "final_response": final_response,
        "current_agent": "end"
    }


def _generate_summary(client, state: Dict[str, Any], entities: Dict) -> str:
    """Generate a concise conversation summary using Gemini."""
    is_scam = state.get("scam_detected", False)
    scam_type = state.get("scam_type", "Unknown")
    conversation_history = state.get("conversation_history", [])
    
    # If not a scam, return simple message
    if not is_scam:
        return "Message analyzed and determined to be non-malicious. No scam indicators detected."
    
    # Format conversation for Gemini
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
    
    return _call_gemini_with_retry(client, prompt)


def _fallback_summary(state: Dict[str, Any], entities: Dict) -> str:
    """Generate fallback summary when Gemini is unavailable."""
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
