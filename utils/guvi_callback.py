"""
GUVI Final Result Callback.
Mandatory callback to report extracted intelligence for evaluation (Section 12).
"""

import httpx
import logging
from typing import Dict, Any, List, Optional
from config import get_settings

logger = logging.getLogger(__name__)

# GUVI_CALLBACK_URL = "https://hackathon.guvi.in/api/updateHoneyPotFinalResult" # Removed hardcoded URL
CALLBACK_TIMEOUT = 10  # seconds


async def send_guvi_callback(
    session_id: str,
    scam_detected: bool,
    total_messages: int,
    extracted_intelligence: Dict[str, List[str]],
    agent_notes: str,
    scam_indicators: Optional[List[str]] = None
) -> bool:
    """
    Send final result to GUVI evaluation endpoint.
    
    This callback is MANDATORY for evaluation (Section 12).
    Must be called after:
    - Scam intent is confirmed
    - AI Agent has completed engagement
    - Intelligence extraction is finished
    
    Args:
        session_id: Unique session ID from the platform
        scam_detected: Whether scam intent was confirmed
        total_messages: Total messages exchanged in the session
        extracted_intelligence: Dictionary with extracted entities
        agent_notes: Summary of scammer behavior
        scam_indicators: List of suspicious keywords/patterns found
        
    Returns:
        True if callback succeeded, False otherwise
    """
    # Helper to flatten entities (since they might be stored as {"value": "..."} dicts)
    def flatten(items):
        if not isinstance(items, list):
            return []
        return [item.get("value", str(item)) if isinstance(item, dict) else str(item) for item in items]

    # Build payload per Section 12 specification
    payload = {
        "sessionId": session_id,
        "scamDetected": scam_detected,
        "totalMessagesExchanged": total_messages,
        "extractedIntelligence": {
            "bankAccounts": flatten(extracted_intelligence.get("bank_accounts", [])),
            "upiIds": flatten(extracted_intelligence.get("upi_ids", [])),
            "phishingLinks": flatten(extracted_intelligence.get("phishing_urls", [])),
            "phoneNumbers": flatten(extracted_intelligence.get("phone_numbers", [])),
            "emailAddresses": flatten(extracted_intelligence.get("email_addresses", [])),
            "suspiciousKeywords": scam_indicators or flatten(extracted_intelligence.get("keywords", []))
        },
        "agentNotes": agent_notes
    }
    
    # Log full payload for debugging
    import json
    
    # Get URL from .env with fallback to hardcoded URL
    settings = get_settings()
    callback_url = settings.guvi_callback_url or "https://hackathon.guvi.in/api/updateHoneyPotFinalResult"
    
    if not settings.guvi_callback_url:
        logger.warning("GUVI_CALLBACK_URL not set in .env, using fallback URL")
    
    from utils.logger import AgentLogger
    
    AgentLogger._print_colored("GUVI", "purple", "📞", f"Sending Report: URL: {callback_url}")
    # Log payload as debug unless it's small, or just print it cleanly
    # logger.debug(json.dumps(payload, indent=2))
    print(f"\033[95m{json.dumps(payload, indent=2)}\033[0m") # Print payload in purple directly for visibility per user request
    
    try:
        async with httpx.AsyncClient(timeout=CALLBACK_TIMEOUT) as client:
            response = await client.post(
                callback_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                AgentLogger._print_colored("GUVI", "purple", "✅", f"Success: Status: {response.status_code}")
                return True
            else:
                AgentLogger._print_colored("GUVI", "purple", "❌", f"Failed: Status: {response.status_code} | Body: {response.text}")
                return False
                
    except httpx.TimeoutException:
        AgentLogger._print_colored("GUVI", "red", "⏱️", "Timeout", f"Failed to reach {callback_url}")
        return False
    except Exception as e:
        logger.error(f"[GUVI CALLBACK] ❌ ERROR - {type(e).__name__}: {e}")
        return False


def build_agent_notes(
    scam_type: Optional[str],
    behavioral_signals: List[str],
    conversation_summary: str
) -> str:
    """
    Build human-readable agent notes for GUVI callback.
    
    Args:
        scam_type: Detected type of scam
        behavioral_signals: Psychological triggers identified
        conversation_summary: AI-generated summary
        
    Returns:
        Formatted agent notes string
    """
    parts = []
    
    if scam_type:
        parts.append(f"Scam Type: {scam_type}")
        
    if behavioral_signals:
        tactics = ", ".join(behavioral_signals[:5])  # Limit to top 5
        parts.append(f"Tactics Used: {tactics}")
        
    if conversation_summary:
        # Truncate if too long
        summary = conversation_summary[:200] + "..." if len(conversation_summary) > 200 else conversation_summary
        parts.append(summary)
    
    return " | ".join(parts) if parts else "Scam detected and engaged by honeypot agent."
