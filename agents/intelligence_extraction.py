"""
Intelligence Extraction Agent
Extracts bank accounts, UPI IDs, and phishing URLs from conversation history.
Uses OpenAI for intelligent extraction with error handling and retry logic.
"""

import json
import logging
from typing import Dict, Any
from utils.llm_client import call_llm
from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

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
    Extract intelligence entities from conversation history using OpenAI.
    """
    
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
        # Extract using OpenAI
        prompt = EXTRACTION_PROMPT.format(conversation=all_text[:8000])  # Limit context
        response_text = call_llm(
            prompt=prompt,
            system_instruction="You are an expert intelligence extractor.",
            json_mode=True
        )
        
        extracted_data = _parse_json_safely(response_text) # Replaced json.loads with _parse_json_safely
        
        # Transparent Logging
        from utils.logger import AgentLogger
        AgentLogger.extraction_result(extracted_data)
        
        return {
            "extracted_entities": extracted_data,
            "extraction_complete": False,
            "current_agent": "agentic_judge" # Updated from "confidence_scoring"
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
            "extraction_complete": False,
            "current_agent": "agentic_judge", # Updated from "confidence_scoring"
            "error": str(e)
        }
