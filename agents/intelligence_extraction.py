"""
Intelligence Extraction Agent
Extracts bank accounts, UPI IDs, and phishing URLs from conversation history.
Uses Gemini for intelligent extraction with error handling and retry logic.
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional
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
        # Return empty extraction on parse error
        return {
            "bank_accounts": [],
            "upi_ids": [],
            "phishing_urls": [],
            "notes": "Failed to parse AI response"
        }


EXTRACTION_PROMPT = """You are an intelligence extraction system. Analyze this conversation for scam-related entities.

CONVERSATION:
{conversation}

Extract and validate:
1. Bank Account Numbers: 9-18 digit numbers that appear to be bank accounts
2. UPI IDs: Patterns like xxx@upi, xxx@paytm, xxx@gpay, xxx@ybl, etc.
3. Phishing URLs: Suspicious URLs that could be used for phishing (exclude legitimate domains like google.com, facebook.com, etc.)

Be thorough and extract ALL entities mentioned in the conversation.

Respond with ONLY a valid JSON object:
{{
    "bank_accounts": ["list of account numbers as strings"],
    "upi_ids": ["list of UPI IDs"],
    "phishing_urls": ["list of URLs"],
    "notes": "Brief notes on what was extracted"
}}"""


def intelligence_extraction_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract intelligence entities from conversation history using Gemini.
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with extracted entities
    """
    client = _get_gemini_client()
    if not client:
        raise RuntimeError("Gemini API client not initialized. Please set GOOGLE_API_KEY in .env")
    
    conversation_history = state.get("conversation_history", [])
    original_message = state.get("original_message", "")
    
    # Combine all text for extraction
    all_text = f"Original scam message: {original_message}\n\n"
    for turn in conversation_history:
        role = "Honeypot" if turn.get("role") == "honeypot" else "Scammer"
        all_text += f"{role}: {turn.get('message', '')}\n"
        
        # Also include revealed_info from mock scammer
        revealed = turn.get("revealed_info", {})
        if revealed:
            all_text += f"[Revealed Info: {json.dumps(revealed)}]\n"
    
    try:
        # Extract using Gemini
        prompt = EXTRACTION_PROMPT.format(conversation=all_text[:8000])  # Limit context
        response_text = _call_gemini_with_retry(client, prompt)
        result = _parse_json_safely(response_text)
        
        extracted = {
            "bank_accounts": result.get("bank_accounts", []),
            "upi_ids": result.get("upi_ids", []),
            "phishing_urls": result.get("phishing_urls", [])
        }
        
        return {
            "extracted_entities": extracted,
            "extraction_complete": True,
            "current_agent": "confidence_scoring"
        }
        
    except Exception as e:
        logger.error(f"Intelligence extraction failed: {e}")
        # Return empty extraction on error
        return {
            "extracted_entities": {
                "bank_accounts": [],
                "upi_ids": [],
                "phishing_urls": []
            },
            "extraction_complete": True,
            "current_agent": "confidence_scoring",
            "error": str(e)
        }
