"""
Scam Detection Agent
Uses Google Gemini to analyze incoming messages for scam indicators.
Includes error handling, retry logic, and input sanitization.
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


def _sanitize_input(message: str) -> str:
    """Sanitize input to prevent prompt injection."""
    # Limit length
    message = message[:settings.max_message_length]
    # Remove potential prompt injection patterns
    message = message.replace("```", "")
    message = message.replace("SYSTEM:", "")
    message = message.replace("USER:", "")
    message = message.replace("ASSISTANT:", "")
    return message.strip()


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


def _parse_json_safely(response_text: str) -> Dict[str, Any]:
    """Safely parse JSON response with fallback handling."""
    # Handle markdown code blocks
    if response_text.startswith("```"):
        parts = response_text.split("```")
        if len(parts) >= 2:
            response_text = parts[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
    
    response_text = response_text.strip()
    
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}, raw text: {response_text[:200]}")
        # Return safe default
        return {
            "is_scam": False,
            "scam_type": None,
            "confidence": 0.0,
            "indicators": [],
            "reasoning": "Failed to parse AI response"
        }


SCAM_DETECTION_PROMPT = """You are an expert scam detection system. Analyze the following message and determine if it is a scam attempt.

MESSAGE TO ANALYZE:
{message}

Analyze for these scam indicators:
1. LOTTERY_FRAUD: Claims of winning prizes, lotteries, or lucky draws
2. UPI_FRAUD: Requests for UPI payments, processing fees, or advance payments
3. BANK_IMPERSONATION: Pretending to be from banks, asking for KYC/verification
4. PHISHING: Suspicious links, fake websites, credential harvesting
5. INVESTMENT_SCAM: Get-rich-quick schemes, unrealistic returns
6. TECH_SUPPORT_SCAM: Fake tech support, virus warnings
7. ROMANCE_SCAM: Suspicious relationship-based money requests
8. JOB_SCAM: Fake job offers requiring upfront payments

Respond ONLY with a valid JSON object in this exact format:
{{
    "is_scam": true/false,
    "scam_type": "TYPE_FROM_ABOVE or null",
    "confidence": 0.0-1.0,
    "indicators": ["list", "of", "specific", "indicators", "found"],
    "reasoning": "Brief explanation of your analysis"
}}

Important: Respond ONLY with the JSON, no other text."""


def scam_detection_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze the incoming message for scam indicators using Gemini.
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with scam detection results
    """
    message = state.get("original_message", "")
    
    # Sanitize input
    message = _sanitize_input(message)
    
    client = _get_gemini_client()
    if not client:
        raise RuntimeError("Gemini API client not initialized. Please set GOOGLE_API_KEY in .env")
    
    prompt = SCAM_DETECTION_PROMPT.format(message=message)
    
    try:
        response_text = _call_gemini_with_retry(client, prompt)
        analysis = _parse_json_safely(response_text)
        
        is_scam = analysis.get("is_scam", False)
        confidence = float(analysis.get("confidence", 0.0))
        
        # Check against threshold
        if is_scam and confidence >= settings.scam_detection_threshold:
            return {
                "scam_detected": True,
                "scam_type": analysis.get("scam_type"),
                "scam_indicators": analysis.get("indicators", []),
                "confidence_score": confidence,
                "current_agent": "persona_engagement"
            }
        else:
            return {
                "scam_detected": False,
                "scam_type": None,
                "scam_indicators": analysis.get("indicators", []),
                "confidence_score": confidence,
                "current_agent": "response_formatter"
            }
            
    except Exception as e:
        logger.error(f"Scam detection failed: {e}")
        # Return safe default on error
        return {
            "scam_detected": False,
            "scam_type": None,
            "scam_indicators": [],
            "confidence_score": 0.0,
            "current_agent": "response_formatter",
            "error": str(e)
        }
