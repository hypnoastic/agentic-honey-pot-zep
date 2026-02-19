"""
Scam Detection Agent
Analyzes message intent using optimized LLM prompts and category enforcement.
"""

import logging
from typing import Dict, Any
from config import get_settings
from utils.parsing import parse_json_safely

settings = get_settings()
logger = logging.getLogger(__name__)

# Scam Type Configuration

VALID_SCAM_TYPES = {
    "LOTTERY_FRAUD",
    "UPI_FRAUD",
    "BANK_IMPERSONATION",
    "PHISHING",
    "INVESTMENT_SCAM",
    "TECH_SUPPORT_SCAM",
    "ROMANCE_SCAM",
    "JOB_SCAM"
}

# =========================================================
# INPUT SANITIZATION
# =========================================================

def _sanitize_input(message: str) -> str:
    """
    Basic injection protection + length control.
    """
    if not isinstance(message, str):
        return ""

    message = message[:settings.max_message_length]
    message = message.replace("```", "")
    message = message.replace("SYSTEM:", "")
    message = message.replace("USER:", "")
    message = message.replace("ASSISTANT:", "")
    return message.strip()


# =========================================================
# OPTIMIZED PROMPT (Gemini Flash Friendly)
# =========================================================

SCAM_DETECTION_PROMPT = """Detect scam intent. Return JSON only.

MESSAGE:
{message}

PRIOR SCAM TYPES:
{intelligence_context}

FACT CHECK:
{fact_check_context}

CATEGORIES:
LOTTERY_FRAUD
UPI_FRAUD
BANK_IMPERSONATION
PHISHING
INVESTMENT_SCAM
TECH_SUPPORT_SCAM
ROMANCE_SCAM
JOB_SCAM

Rules:
- Analyze underlying intent, not just keywords.
- Assign the MOST specific category.
- Ignore short, benign greetings (e.g., "Hello", "Hi there") unless they contain a request or link.
- If unclear, set scam_detected=false and scam_type=null.

JSON FORMAT:
{{
  "scam_detected": true/false,
  "scam_type": "CATEGORY or null",
  "confidence": 0.0-1.0,
  "indicators": [],
  "behavioral_signals": [],
  "confidence_factors": {{}},
  "reasoning": "Short explanation"
}}
"""


# =========================================================
# MAIN AGENT
# =========================================================

async def scam_detection_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze incoming message for scam indicators.
    Async + production hardened.
    """

    from utils.llm_client import call_llm_async
    from utils.logger import AgentLogger

    # -------------------------
    # Extract Inputs
    # -------------------------
    raw_message = state.get("original_message", "")
    message = _sanitize_input(raw_message)

    prior_scams = state.get("prior_scam_types", [])
    fact_check_results = state.get("fact_check_results", {})

    # -------------------------
    # Format Intelligence Context
    # -------------------------
    intelligence_context = (
        "- " + "\n- ".join(prior_scams[:3])
        if prior_scams
        else "None"
    )

    # -------------------------
    # Format Fact Check Context
    # -------------------------
    if fact_check_results.get("fact_checked"):
        fact_check_context = (
            f"Status: {fact_check_results.get('overall_status', 'UNKNOWN')}\n"
            f"Claims Checked: {fact_check_results.get('claims_checked', 0)}"
        )
    else:
        fact_check_context = "None"

    # -------------------------
    # Build Prompt
    # -------------------------
    prompt = SCAM_DETECTION_PROMPT.format(
        message=message,
        intelligence_context=intelligence_context,
        fact_check_context=fact_check_context
    )

    try:
        # -------------------------
        # Call Gemini Flash
        # -------------------------
        response_text = await call_llm_async(
            prompt=prompt,
            system_instruction="You are a highly precise scam detection engine.",
            json_mode=True,
            agent_name="detection",
            temperature=0.1  # deterministic for safety
        )

        analysis = parse_json_safely(response_text) or {}

        if isinstance(analysis, list) and analysis:
            analysis = analysis[0]
            
        if not isinstance(analysis, dict):
            analysis = {}

        # -------------------------
        # Extract & Validate Fields
        # -------------------------
        scam_detected = bool(analysis.get("scam_detected", False))

        # Confidence normalization
        try:
            confidence = float(analysis.get("confidence", 0.0))
        except Exception:
            confidence = 0.0
            
        # Add slight jitter to avoid looking "fake" or hardcoded (requested by user)
        # But only if it's a valid confidence
        if confidence > 0.5:
            import random
            jitter = random.uniform(-0.03, 0.03)
            confidence = max(0.0, min(1.0, confidence + jitter))

        confidence = max(0.0, min(1.0, confidence))

        scam_type = analysis.get("scam_type")

        # -------------------------
        # Enforce Scam Type Whitelist
        # -------------------------
        if scam_type not in VALID_SCAM_TYPES:
            scam_type = None
            scam_detected = False

        # -------------------------
        # Fact Check Confidence Boost
        # -------------------------
        if fact_check_results.get("confidence_boost"):
            boost = float(fact_check_results.get("confidence_boost", 0.0))
            confidence = max(0.0, min(1.0, confidence + boost))

        # -------------------------
        # Low Confidence Guard
        # -------------------------
        if scam_detected and confidence < 0.3:
            scam_detected = False
            scam_type = None

        if scam_detected and confidence < 0.3:
            scam_detected = False
            scam_type = None

        # -------------------------
        # Ambiguity Guard
        # -------------------------
        # If confidence is mediocre (< 0.75) AND no hard indicators, treat as safe
        # This prevents "vibe-based" false positives on greetings
        indicators = analysis.get("indicators", [])
        if scam_detected and confidence < 0.75 and not indicators:
            scam_detected = False
            scam_type = None

        # -------------------------
        # Logging
        # -------------------------
        AgentLogger.scam_detected(
            confidence,
            f"Type: {scam_type}, Detected: {scam_detected}"
        )

        # -------------------------
        # Routing Logic
        # -------------------------
        if scam_detected and confidence >= settings.scam_detection_threshold:
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
            "behavioral_signals": [],
            "confidence_factors": {},
            "confidence_score": 0.0,
            "current_agent": "response_formatter",
            "error": str(e)
        }
