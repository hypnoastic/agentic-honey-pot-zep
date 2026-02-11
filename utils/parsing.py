"""
Shared parsing utilities for the Agentic Honey-Pot system.
"""

import json
import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)

def parse_json_safely(response_text: str) -> Dict[str, Any]:
    """
    Safely parse JSON response from LLM with robust cleaning.
    Handles markdown code blocks and common formatting issues.
    """
    if not response_text:
        return {}

    # Handle markdown code blocks
    if "```" in response_text:
        # Match content between ```json and ``` or just ``` and ```
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", response_text, re.DOTALL)
        if match:
            response_text = match.group(1)
        else:
            # Fallback: remove the triple backticks manually
            response_text = response_text.replace("```json", "").replace("```", "").strip()
    
    response_text = response_text.strip()
    
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}, raw text: {response_text[:200]}")
        
        # Try a more aggressive cleanup if simple parsing fails
        # Sometimes there's text before or after the JSON object
        try:
            match = re.search(r"(\{.*\})", response_text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        except Exception:
            pass
            
        return {}
