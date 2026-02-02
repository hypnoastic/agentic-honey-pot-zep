"""
Safe Response Utility.
Guarantees valid JSON output for the API, even in case of catastrophic failure.
"""

import logging
import uuid
from typing import Dict, Any, Optional

from fastapi.responses import JSONResponse
from models.schemas import AnalyzeResponse, ExtractedEntities

logger = logging.getLogger(__name__)

def create_fallback_response(conversation_id: str, error_msg: str) -> AnalyzeResponse:
    """
    Create a safe fallback response when the system fails.
    Returns a valid AnalyzeResponse object with default safe values.
    """
    return AnalyzeResponse(
        is_scam=False,
        scam_type=None,
        confidence_score=0.0,
        extracted_entities=ExtractedEntities(
            bank_accounts=[],
            upi_ids=[],
            phishing_urls=[]
        ),
        behavioral_signals=[],
        confidence_factors={"error": "System fail-safe triggered"},
        agent_reply="I am currently experiencing technical difficulties. Please try again later.",
        conversation_id=conversation_id
    )

def construct_safe_response(result: Dict[str, Any], conversation_id: str) -> AnalyzeResponse:
    """
    Construct a valid AnalyzeResponse from the workflow result.
    Validates required fields and applies defaults where missing.
    """
    try:
        # Validate extracted entities structure
        entities_data = result.get("extracted_entities", {})
        if not isinstance(entities_data, dict):
            entities_data = {}
            
        extracted_entities = ExtractedEntities(
            bank_accounts=entities_data.get("bank_accounts", []) or [],
            upi_ids=entities_data.get("upi_ids", []) or [],
            phishing_urls=entities_data.get("phishing_urls", []) or []
        )

        return AnalyzeResponse(
            is_scam=bool(result.get("is_scam", False)),
            scam_type=str(result.get("scam_type")) if result.get("scam_type") else None,
            confidence_score=float(result.get("confidence_score", 0.0)),
            extracted_entities=extracted_entities,
            behavioral_signals=list(result.get("behavioral_signals", []) or []),
            confidence_factors=dict(result.get("confidence_factors", {}) or {}),
            agent_reply=str(result.get("agent_response")) if result.get("agent_response") else None,
            conversation_id=conversation_id
        )
    except Exception as e:
        logger.error(f"Error constructing safe response: {e}")
        return create_fallback_response(conversation_id, str(e))

async def safe_analyze_wrapper(func, *args, **kwargs) -> AnalyzeResponse:
    """
    Wrapper to execute the analysis function safely.
    Catches ALL exceptions and returns a fallback JSON response.
    """
    conversation_id = kwargs.get("conversation_id") or str(uuid.uuid4())
    
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        logger.exception(f"Critical System Failure in {func.__name__}: {e}")
        return create_fallback_response(conversation_id, str(e))
