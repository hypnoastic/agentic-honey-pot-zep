"""
Safe Response Utility.
Guarantees valid JSON output for the API, matching Section 8: {"status": "success", "reply": "..."}
"""

import logging
import uuid
from typing import Dict, Any, Optional

from models.schemas import AnalyzeResponse

logger = logging.getLogger(__name__)


def create_fallback_response(error_msg: str = "") -> AnalyzeResponse:
    """
    Create a safe fallback response when the system fails.
    Returns minimal response with error status.
    """
    return AnalyzeResponse(
        status="error",
        reply="I am currently experiencing technical difficulties. Please try again later."
    )


def construct_safe_response(result: Dict[str, Any], conversation_id: str) -> AnalyzeResponse:
    """
    Construct a valid AnalyzeResponse from the workflow result.
    Optimized to pull from both top-level state and nested final_response.
    """
    try:
        # 1. Get nested response if available (from response_formatter)
        final = result.get("final_response", {})
        
        # 2. Extract fields (Prioritizing nested 'final' over top-level state)
        reply = final.get("reply") or final.get("agent_response") or result.get("agent_response") or result.get("reply")
        scam_detected = final.get("scam_detected")
        if scam_detected is None:
            scam_detected = result.get("scam_detected", False)
            
        scam_type = final.get("scam_type") or result.get("scam_type")
        entities = final.get("extracted_entities") or result.get("extracted_entities", {})
        turns = final.get("engagement_count") or result.get("engagement_count", 0)
        
        return AnalyzeResponse(
            status="success",
            reply=str(reply) if reply else None,
            scam_detected=bool(scam_detected),
            scam_type=scam_type,
            extracted_entities=entities,
            engagement_count=int(turns)
        )
    except Exception as e:
        logger.error(f"Error constructing safe response: {e}")
        return create_fallback_response(str(e))


async def safe_analyze_wrapper(func, *args, **kwargs) -> AnalyzeResponse:
    """
    Wrapper to execute the analysis function safely.
    Catches ALL exceptions and returns a fallback JSON response.
    """
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        logger.exception(f"Critical System Failure in {func.__name__}: {e}")
        return create_fallback_response(str(e))


