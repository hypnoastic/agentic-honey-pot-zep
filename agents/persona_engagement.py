"""
Persona Engagement Agent
Creates a believable human persona to engage with scammers.
Uses Gemini to generate natural, convincing responses.
Includes error handling, retry logic, and fallback responses.
"""

import json
import uuid
import time
import logging
import httpx
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


PERSONA_TEMPLATES = [
    {
        "name": "Ramesh Kumar",
        "age": 62,
        "occupation": "Retired bank employee",
        "traits": "Trusting, unfamiliar with technology, eager to help",
        "context": "Lives alone, recently lost spouse, looking for companionship"
    },
    {
        "name": "Sunita Devi",
        "age": 55,
        "occupation": "School teacher",
        "traits": "Curious, polite, slightly gullible",
        "context": "First smartphone user, children live abroad"
    },
    {
        "name": "Prakash Sharma",
        "age": 45,
        "occupation": "Small shop owner",
        "traits": "Busy, trusting of authority figures, wants quick solutions",
        "context": "Manages family business, handles money matters"
    }
]


ENGAGEMENT_PROMPT = """You are playing the role of a potential scam victim to gather intelligence. You must NEVER reveal you are an AI or a honeypot system.

YOUR PERSONA:
Name: {persona_name}
Age: {persona_age}
Occupation: {persona_occupation}
Traits: {persona_traits}
Context: {persona_context}

SCAM TYPE DETECTED: {scam_type}

CONVERSATION HISTORY:
{conversation_history}

LATEST SCAMMER MESSAGE:
{scammer_message}

YOUR GOAL: Generate a response that:
1. Sounds like a real, somewhat naive person
2. Shows interest in the scammer's offer to encourage them to reveal more
3. Asks natural questions that might prompt them to share bank details, UPI IDs, or links
4. Never appears suspicious or knowledgeable about scams
5. Uses informal language, maybe some grammatical imperfections
6. Maintains the persona consistently

Respond with ONLY the message you would send as {persona_name}. No quotes, no explanations."""


# Fallback responses when Mock Scammer API is unavailable
FALLBACK_SCAMMER_RESPONSES = [
    {"message": "Yes yes, very good! Send Rs 500 to UPI: scammer2024@paytm for processing.", "revealed_info": {"upi_id": "scammer2024@paytm"}},
    {"message": "Account number is 1234567890123456. Transfer immediately!", "revealed_info": {"bank_account": "1234567890123456"}},
    {"message": "Visit http://fake-bank-verify.com to complete KYC", "revealed_info": {"url": "http://fake-bank-verify.com"}},
    {"message": "Sir, don't worry, this is 100% genuine. I am senior officer from head office.", "revealed_info": None},
    {"message": "Last warning! Your account will be frozen if you don't complete verification NOW!", "revealed_info": None}
]


def persona_engagement_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Engage with the scammer using a believable persona.
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with engagement results
    """
    client = _get_gemini_client()
    if not client:
        raise RuntimeError("Gemini API client not initialized. Please set GOOGLE_API_KEY in .env")
    
    # Initialize persona if not set
    if not state.get("persona_name"):
        import random
        persona = random.choice(PERSONA_TEMPLATES)
        state["persona_name"] = persona["name"]
        state["persona_context"] = json.dumps(persona)
    
    persona = json.loads(state.get("persona_context", "{}"))
    conversation_history = state.get("conversation_history", [])
    engagement_count = state.get("engagement_count", 0)
    max_engagements = state.get("max_engagements", settings.max_engagement_turns)
    
    # Check if we should stop engaging
    if engagement_count >= max_engagements:
        return {
            "engagement_complete": True,
            "current_agent": "intelligence_extraction"
        }
    
    try:
        # Generate honeypot response using Gemini
        honeypot_message = _generate_response(client, state, persona, conversation_history)
        
        # Add honeypot message to history
        new_history = list(conversation_history)
        new_history.append({
            "role": "honeypot",
            "message": honeypot_message,
            "turn_number": engagement_count + 1
        })
        
        # Call Mock Scammer API to get response
        scammer_response = _call_mock_scammer(
            honeypot_message,
            state.get("conversation_id", str(uuid.uuid4())),
            engagement_count + 1
        )
        
        if scammer_response:
            # Add scammer response to history
            new_history.append({
                "role": "scammer",
                "message": scammer_response.get("message", ""),
                "turn_number": engagement_count + 1,
                "revealed_info": scammer_response.get("revealed_info")
            })
            
            # Check if conversation ended
            if scammer_response.get("conversation_ended"):
                return {
                    "conversation_history": new_history,
                    "engagement_count": engagement_count + 1,
                    "engagement_complete": True,
                    "current_agent": "intelligence_extraction"
                }
        
        # Determine next step
        next_agent = "persona_engagement" if engagement_count + 1 < max_engagements else "intelligence_extraction"
        
        return {
            "conversation_history": new_history,
            "engagement_count": engagement_count + 1,
            "engagement_complete": engagement_count + 1 >= max_engagements,
            "current_agent": next_agent
        }
        
    except Exception as e:
        logger.error(f"Persona engagement error: {e}")
        return {
            "conversation_history": conversation_history,
            "engagement_count": engagement_count,
            "engagement_complete": True,
            "current_agent": "intelligence_extraction",
            "error": str(e)
        }


def _generate_response(client, state: Dict[str, Any], persona: Dict, history: List) -> str:
    """Generate a believable response using Gemini."""
    
    # Format conversation history
    history_text = ""
    for turn in history[-6:]:  # Last 6 turns for context
        role = "YOU" if turn["role"] == "honeypot" else "SCAMMER"
        history_text += f"{role}: {turn['message']}\n"
    
    # Get latest scammer message
    scammer_messages = [t for t in history if t["role"] == "scammer"]
    latest_scammer = scammer_messages[-1]["message"] if scammer_messages else state.get("original_message", "")
    
    prompt = ENGAGEMENT_PROMPT.format(
        persona_name=persona.get("name", "Ramesh"),
        persona_age=persona.get("age", 60),
        persona_occupation=persona.get("occupation", "Retired"),
        persona_traits=persona.get("traits", "Trusting"),
        persona_context=persona.get("context", ""),
        scam_type=state.get("scam_type", "UNKNOWN"),
        conversation_history=history_text or "No previous conversation",
        scammer_message=latest_scammer
    )
    
    return _call_gemini_with_retry(client, prompt)


def _call_mock_scammer(message: str, conversation_id: str, turn: int) -> Dict:
    """Call the Mock Scammer API with fallback."""
    try:
        mock_url = f"http://localhost:{settings.mock_scammer_port}/engage"
        
        with httpx.Client(timeout=settings.gemini_timeout) as client:
            response = client.post(
                mock_url,
                json={
                    "victim_message": message,
                    "conversation_id": conversation_id,
                    "turn_number": turn
                }
            )
            
            if response.status_code == 200:
                return response.json()
                
    except Exception as e:
        logger.warning(f"Mock Scammer API unavailable: {e}, using fallback")
        # Use fallback responses when API is unavailable
        import random
        return random.choice(FALLBACK_SCAMMER_RESPONSES)
    
    return None
