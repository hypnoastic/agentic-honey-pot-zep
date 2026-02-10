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
    Returns only status and reply per Section 8.
    """
    try:
        # Extract reply from agent_response (internal name)
        agent_reply = result.get("agent_response") or result.get("reply")
        
        return AnalyzeResponse(
            status="success",
            reply=str(agent_reply) if agent_reply else None,
            scam_detected=result.get("is_scam", False),
            engagement_count=result.get("engagement_count", 0)
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


