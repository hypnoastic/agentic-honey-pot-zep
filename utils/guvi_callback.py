"""
GUVI Final Result Callback.
Mandatory callback to report extracted intelligence for evaluation (Section 12).
"""

import httpx
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

GUVI_CALLBACK_URL = "https://hackathon.guvi.in/api/updateHoneyPotFinalResult"
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
    # Build payload per Section 12 specification
    payload = {
        "sessionId": session_id,
        "scamDetected": scam_detected,
        "totalMessagesExchanged": total_messages,
        "extractedIntelligence": {
            "bankAccounts": extracted_intelligence.get("bank_accounts", []),
            "upiIds": extracted_intelligence.get("upi_ids", []),
            "phishingLinks": extracted_intelligence.get("phishing_urls", []),
            "phoneNumbers": extracted_intelligence.get("phone_numbers", []),
            "suspiciousKeywords": scam_indicators or extracted_intelligence.get("keywords", [])
        },
        "agentNotes": agent_notes
    }
    
    # Log full payload for debugging
    import json
    logger.info("=" * 60)
    logger.info("[GUVI CALLBACK] SENDING FINAL RESULT TO HACKATHON ENDPOINT")
    logger.info(f"[GUVI CALLBACK] URL: {GUVI_CALLBACK_URL}")
    logger.info(f"[GUVI CALLBACK] Session ID: {session_id}")
    logger.info(f"[GUVI CALLBACK] Scam Detected: {scam_detected}")
    logger.info(f"[GUVI CALLBACK] Total Messages: {total_messages}")
    logger.info(f"[GUVI CALLBACK] Full Payload:")
    logger.info(json.dumps(payload, indent=2))
    logger.info("=" * 60)
    
    try:
        async with httpx.AsyncClient(timeout=CALLBACK_TIMEOUT) as client:
            response = await client.post(
                GUVI_CALLBACK_URL,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                logger.info(f"[GUVI CALLBACK] ✅ SUCCESS - Status: {response.status_code}")
                logger.info(f"[GUVI CALLBACK] Response: {response.text[:200] if response.text else 'OK'}")
                return True
            else:
                logger.warning(f"[GUVI CALLBACK] ❌ FAILED - Status: {response.status_code}")
                logger.warning(f"[GUVI CALLBACK] Response Body: {response.text}")
                return False
                
    except httpx.TimeoutException:
        logger.error(f"[GUVI CALLBACK] ⏱️ TIMEOUT - Failed to reach {GUVI_CALLBACK_URL}")
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
