"""
Scam Detection Agent
Uses LLM to analyze incoming messages for scam indicators.
Integrates with fact-checker for internet verification of claims.
"""

import json
import asyncio
import logging
from typing import Dict, Any
from utils.llm_client import call_llm
from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _sanitize_input(message: str) -> str:
    """Sanitize input to prevent prompt injection."""
    message = message[:settings.max_message_length]
    message = message.replace("```", "")
    message = message.replace("SYSTEM:", "")
    message = message.replace("USER:", "")
    message = message.replace("ASSISTANT:", "")
    return message.strip()


def _parse_json_safely(response_text: str) -> Dict[str, Any]:
    """Safely parse JSON response with fallback handling."""
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

CONTEXTUAL INTELLIGENCE (Similar past scams):
{intelligence_context}

{fact_check_context}

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
    "behavioral_signals": ["list", "of", "psychological", "triggers", "e.g. Urgency, Greed"],
    "confidence_factors": {{"Specific Keyword": 0.0-1.0, "Link Analysis": 0.0-1.0}},
    "reasoning": "Brief explanation of your analysis"
}}

Important: Respond ONLY with the JSON, no other text."""


def scam_detection_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze the incoming message for scam indicators using GPT-5-mini.
    Integrates fact-checker results if available.
    """
    message = state.get("original_message", "")
    prior_scams = state.get("prior_scam_types", [])
    
    # Format intelligence context
    if prior_scams:
        intel_ctx = "- " + "\n- ".join(prior_scams[:3])
    else:
        intel_ctx = "No specific prior intelligence available."
    
    # Intelligence Context is already loaded into state
    intel_ctx = "- " + "\n- ".join(prior_scams[:3]) if prior_scams else "No specific prior intelligence available."
    
    # Format fact-check context if available
    fact_check_results = state.get("fact_check_results", {})
    if fact_check_results.get("fact_checked"):
        fact_check_context = f"""
INTERNET VERIFICATION RESULTS:
Status: {fact_check_results.get('overall_status', 'UNKNOWN')}
Claims Checked: {fact_check_results.get('claims_checked', 0)}
"""
        for result in fact_check_results.get("results", [])[:2]:
            fact_check_context += f"- {result.get('claim', '')}: {result.get('status', 'UNKNOWN')}\n"
    else:
        fact_check_context = ""
    
    # Sanitize input
    message = _sanitize_input(message)
    
    prompt = SCAM_DETECTION_PROMPT.format(
        message=message,
        intelligence_context=intel_ctx,
        fact_check_context=fact_check_context
    )
    
    try:
        response_text = call_llm(
            prompt=prompt,
            system_instruction="You are an expert scam detection AI.",
            json_mode=True,
            agent_name="detection"  # Uses gpt-5-mini
        )
        
        analysis = _parse_json_safely(response_text)
        
        is_scam = analysis.get("is_scam", False)
        confidence = float(analysis.get("confidence", 0.0))
        scam_type = analysis.get("scam_type")
        
        # Apply fact-check confidence boost
        if fact_check_results.get("confidence_boost"):
            confidence = min(1.0, max(0.0, confidence + fact_check_results["confidence_boost"]))
        
        # Transparent Logging
        from utils.logger import AgentLogger
        AgentLogger.scam_detected(confidence, f"Type: {scam_type}, IsScam: {is_scam}")
        
        # Check against threshold
        if is_scam and confidence >= settings.scam_detection_threshold:
            return {
                "scam_detected": True,
                "scam_type": scam_type,
                "scam_indicators": analysis.get("indicators", []),
                "behavioral_signals": analysis.get("behavioral_signals", []),
                "confidence_factors": analysis.get("confidence_factors", {}),
                "confidence_score": confidence,
                "current_agent": "persona_engagement"
            }
        else:
            return {
                "scam_detected": False,
                "scam_type": None,
                "scam_indicators": analysis.get("indicators", []),
                "behavioral_signals": analysis.get("behavioral_signals", []),
                "confidence_factors": analysis.get("confidence_factors", {}),
                "confidence_score": confidence,
                "current_agent": "response_formatter"
            }
            
    except Exception as e:
        logger.error(f"Scam detection failed: {e}")
        return {
            "scam_detected": False,
            "scam_type": None,
            "scam_indicators": [],
            "confidence_score": 0.0,
            "current_agent": "response_formatter",
            "error": str(e)
        }
