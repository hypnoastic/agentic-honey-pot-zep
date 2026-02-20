"""
Safe Response Utility.
Builds the exact HoneypotResponse format required by the scoring rubric.
All 8 entity types, engagementMetrics, agentNotes, scamType, confidenceLevel.
"""

import time
import logging
from typing import Dict, Any, Optional

from models.schemas import (
    HoneypotResponse,
    ExtractedIntelligence,
    AnalyzeResponse,
)

logger = logging.getLogger(__name__)


def _flatten(items) -> list:
    """Flatten entity list — handles both string and {'value': ...} formats."""
    if not isinstance(items, list):
        return []
    result = []
    seen = set()
    for item in items:
        if isinstance(item, dict):
            v = str(item.get("value", "")).strip()
        else:
            v = str(item).strip()
        if v and v not in seen:
            seen.add(v)
            result.append(v)
    return result


def _build_extracted_intelligence(entities: Dict) -> ExtractedIntelligence:
    """
    Build ExtractedIntelligence from internal entity dict.
    Maps internal snake_case keys → camelCase rubric keys.
    Deduplication is enforced via _flatten().
    """
    return ExtractedIntelligence(
        phoneNumbers=_flatten(entities.get("phone_numbers", [])),
        bankAccounts=_flatten(entities.get("bank_accounts", [])),
        upiIds=_flatten(entities.get("upi_ids", [])),
        phishingLinks=_flatten(entities.get("phishing_urls", [])),
        emailAddresses=_flatten(entities.get("email_addresses", [])),
        caseIds=_flatten(entities.get("case_ids", [])),
        policyNumbers=_flatten(entities.get("policy_numbers", [])),
        orderNumbers=_flatten(entities.get("order_numbers", [])),
    )


def _calculate_duration(state: Dict) -> float:
    """Calculate engagement duration in seconds from start_time in state."""
    # Check both top-level and nested final_response dict
    final = state.get("final_response", {}) or {}
    start = state.get("engagement_start_time") or final.get("engagement_start_time")
    if start and isinstance(start, (int, float)) and start > 0:
        return max(0.0, round(time.time() - start, 1))
    return 0.0


def _count_messages(state: Dict) -> int:
    """Count total messages exchanged (scammer + honeypot turns)."""
    final = state.get("final_response", {}) or {}
    # Prefer pre-computed count from formatter
    hist_len = final.get("conversation_history_len")
    if hist_len is not None:
        return int(hist_len) + 1
    history = state.get("conversation_history", [])
    return len(history) + 1 if history is not None else 1


def construct_safe_response(result: Dict[str, Any], conversation_id: str) -> HoneypotResponse:
    """
    Construct a valid HoneypotResponse from the workflow result.
    Pulls from both top-level state and nested final_response.
    """
    try:
        # Get nested final_response if available (from response_formatter)
        # Also check if 'result' itself IS the final_response dict (flat)
        final = result.get("final_response", {}) or result

        # ── Core detection fields ─────────────────────────────────────────────
        scam_detected = final.get("scam_detected")
        if scam_detected is None:
            scam_detected = result.get("scam_detected", False)
        scam_detected = bool(scam_detected)

        scam_type = final.get("scam_type") or result.get("scam_type")

        confidence = final.get("confidence_score") or result.get("confidence_score") or 0.0
        try:
            confidence = float(confidence)
            confidence = round(min(1.0, max(0.0, confidence)), 2)
        except (TypeError, ValueError):
            confidence = 0.0

        # ── Agent reply ───────────────────────────────────────────────────────
        reply = (
            final.get("reply")
            or final.get("agent_response")
            or result.get("agent_response")
            or result.get("reply")
        )

        # ── Intelligence ──────────────────────────────────────────────────────
        entities = final.get("extracted_entities") or result.get("extracted_entities") or {}
        intelligence = _build_extracted_intelligence(entities)

        # ── Engagement metrics ────────────────────────────────────────────────
        duration = _calculate_duration(result)
        total_messages = _count_messages(result)

        # ── Agent notes ───────────────────────────────────────────────────────
        agent_notes = (
            final.get("conversation_summary")
            or result.get("conversation_summary")
            or result.get("judge_reasoning")
        )
        if not agent_notes:
            # Build minimal notes if nothing stored yet
            if scam_detected:
                agent_notes = f"Scam detected: {scam_type or 'Unknown type'}. Honeypot engaged for {total_messages} turns."
            else:
                agent_notes = "No scam detected. Message appears legitimate."

        return HoneypotResponse(
            sessionId=conversation_id,
            model_config={'populate_by_name': True},  # Force camelCase serialization
            scamDetected=scam_detected,
            extractedIntelligence=intelligence,
            engagementDurationSeconds=duration,
            totalMessagesExchanged=total_messages,
            agentNotes=agent_notes,
            scamType=scam_type,
            confidenceLevel=confidence if confidence > 0.0 else None,
            reply=str(reply) if reply else None,
            status="success",
        )

    except Exception as e:
        logger.error(f"Error constructing safe response: {e}")
        return create_fallback_response(str(e), conversation_id)


def create_fallback_response(
    error_msg: str = "", conversation_id: str = ""
) -> HoneypotResponse:
    """
    Create a safe fallback response when the system fails.
    Returns minimal but schema-valid HoneypotResponse.
    """
    return HoneypotResponse(
        sessionId=conversation_id,
        scamDetected=False,
        extractedIntelligence=ExtractedIntelligence(),
        engagementDurationSeconds=0.0,
        totalMessagesExchanged=0,
        agentNotes=f"System error: {error_msg[:200]}" if error_msg else "System error.",
        status="error",
        reply="I am currently experiencing technical difficulties. Please try again.",
    )


async def safe_analyze_wrapper(func, *args, **kwargs):
    """Wrapper to execute the analysis function safely."""
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        logger.exception(f"Critical System Failure in {func.__name__}: {e}")
        return create_fallback_response(str(e))
