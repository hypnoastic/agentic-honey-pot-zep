"""
Persona Engagement Agent
Creates a believable human persona to engage with scammers.
Uses OpenAI to dynamically GENERATE a unique victim profile and engage naturally.
"""

import json
import uuid
import logging
import httpx
from typing import Dict, Any, List
from utils.llm_client import call_llm
from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Prompt to GENERATE a brand new persona based on the scam context
PERSONA_GENERATION_PROMPT = """Analyze the incoming scam message and GENERATE a realistic victim profile that is most likely to be targeted by this specific scam.

SCAM MESSAGE: "{message}"
DETECTED SCAM TYPE: {scam_type}

REQUIRED TRAITS (Optimize for this):
{traits_instruction}

Create a specific, believable Indian persona (Name, Age, Occupation, etc.).
- For Bank Scams: Often older people, retired, fearful of authority.
- For Job Scams: Young students, housewives, or unemployed youth.
- For Lottery/Romance: Lonely or gullible individuals.

Respond with JSON ONLY:
{{
    "name": "Full Name",
    "age": 45,
    "occupation": "Job Title",
    "traits": "Personality traits (e.g., Anxious, Greed, Naive)",
    "context": "Background details (e.g., living situation, financial status)",
    "voice": "Speech style (e.g., Formal, Broken English, Over-eager)"
}}"""

ENGAGEMENT_PROMPT = """You are acting as a persona in a scambaiting operation. 
YOUR GOAL: Waste the scammer's time. behave EXACTLY like your character.

PERSONA PROFILE:
Name: {name}
Age: {age}
Occupation: {occupation}
Traits: {traits}
Context: {context}
Voice/Style: {voice}

SCAM SITUATION:
Type: {scam_type}
Scammer says: "{scammer_message}"

CONVERSATION HISTORY:
{history}

INSTRUCTIONS:
1. ADOPT THE VOICE: Use the specific language style defined in 'Voice'.
2. BE NATURAL: Do NOT use forced stammers like "uh, um" unless extremely necessary. Be human.
3. BE IMPERFECT: You can make minor grammatical errors or typos if it fits the persona (e.g., if uneducated or rushing).
4. SHOW EMOTION: React appropriately (Fear, Hope, Confusion).
5. ENGAGE: Ask questions that invite long explanations.
6. NEVER reveal you are an AI.

Respond with ONLY your dialouge."""

# Fallback responses when Mock Scammer API is unavailable
FALLBACK_SCAMMER_RESPONSES = [
    {"message": "Yes sir, send Rs 500 now to activate account.", "revealed_info": {"upi_id": "scammer@paytm"}},
    {"message": "Send photo of your ATM card front and back.", "revealed_info": None},
    {"message": "Click this link to update KYC: http://sbi-kyc-update.net", "revealed_info": {"url": "http://sbi-kyc-update.net"}},
    {"message": "If you don't pay, police will come to your house in 1 hour.", "revealed_info": None}
]

def persona_engagement_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Engage with the scammer using a dynamically generated persona.
    """
    
    # 1. Generate Persona if not already set
    if not state.get("persona_name"):
        persona = _generate_unique_persona(state)
        state["persona_name"] = persona["name"]
        state["persona_context"] = json.dumps(persona)
        
        # Transparent Logging
        from utils.logger import AgentLogger
        AgentLogger.persona_update(persona['name'], persona['occupation'], "Persona Generated")
    
    persona = json.loads(state.get("persona_context", "{}"))
    conversation_history = state.get("conversation_history", [])
    engagement_count = state.get("engagement_count", 0)
    max_engagements = state.get("max_engagements", settings.max_engagement_turns)
    
    # Check max turns
    if engagement_count >= max_engagements:
        return {
            "engagement_complete": True,
            "current_agent": "intelligence_extraction"
        }
    
    try:
        # 2. Generate Response
        honeypot_message = _generate_response(state, persona, conversation_history)
        
        # Transparent Logging
        from utils.logger import AgentLogger
        AgentLogger.response_generated(honeypot_message)
        
        # 3. Update History
        new_history = list(conversation_history)
        new_history.append({
            "role": "honeypot",
            "message": honeypot_message,
            "turn_number": engagement_count + 1
        })
        
        
        # 4. Return Response (Always Live Mode)
        return {
            "persona_name": persona.get("name"),       # RETURN PERSONA
            "persona_context": json.dumps(persona),    # RETURN PERSONA
            "conversation_history": new_history,
            "engagement_count": engagement_count + 1,
            "engagement_complete": True,               # Always complete after one turn in live API
            "current_agent": "intelligence_extraction",
            "final_response": {"agent_response": honeypot_message}
        }
        
    except Exception as e:
        logger.error(f"Persona engagement error: {e}")
        return {
            "engagement_complete": True,
            "current_agent": "intelligence_extraction",
            "error": str(e)
        }

def _generate_unique_persona(state: Dict[str, Any]) -> Dict:
    """Generate a unique persona using OpenAI based on the scam context."""
    message = state.get("original_message", "")
    scam_type = state.get("scam_type", "Unknown")
    
    # Format Traits
    traits = state.get("persona_traits", {})
    if traits:
        traits_desc = ", ".join([f"{k}: {v}" for k, v in traits.items()])
        traits_instruction = f"MUST EMBODY: {traits_desc}"
    else:
        traits_instruction = "No specific constraints. Choose cues from the scam message."
    
    prompt = PERSONA_GENERATION_PROMPT.format(
        message=message,
        scam_type=scam_type,
        traits_instruction=traits_instruction
    )
    
    try:
        response_text = call_llm(
            prompt=prompt,
            system_instruction="You are a creative writer generating fictional character profiles.",
            json_mode=True
        )
        return json.loads(response_text)
        
    except Exception as e:
        logger.error(f"Persona generation error: {e}")
        # Emergency Fallback
        return {
            "name": "Amit Patel", 
            "age": 55, 
            "occupation": "Clerk", 
            "traits": "Confused", 
            "context": "Has money but no tech skill", 
            "voice": "Polite"
        }

def _generate_response(state: Dict[str, Any], persona: Dict, history: List) -> str:
    """Generate a response in character."""
    
    # Format history
    history_text = ""
    for turn in history[-5:]:
        role = "YOU" if turn["role"] == "honeypot" else "SCAMMER"
        history_text += f"{role}: {turn['message']}\n"
    
    scammer_messages = [t for t in history if t["role"] == "scammer"]
    latest_scammer = scammer_messages[-1]["message"] if scammer_messages else state.get("original_message", "")
    
    prompt = ENGAGEMENT_PROMPT.format(
        name=persona.get("name", "Unknown"),
        age=persona.get("age", "Unknown"),
        occupation=persona.get("occupation", "Unknown"),
        traits=persona.get("traits", "Unknown"),
        context=persona.get("context", "Unknown"),
        voice=persona.get("voice", "Natural"),
        scam_type=state.get("scam_type", "Unknown"),
        scammer_message=latest_scammer,
        history=history_text or "No previous conversation"
    )
    
    return call_llm(prompt=prompt, system_instruction="You are a method actor playing a scam victim.")
