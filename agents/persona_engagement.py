"""
Persona Engagement Agent
Creates a believable human persona to engage with scammers.
Uses OpenAI to dynamically GENERATE a unique victim profile and engage naturally.
"""

import json
import uuid
import random
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

REQUIRED TRAITS (Winning Strategy):
{traits_instruction}

Create a specific, believable Indian persona.
CRITICAL INSTRUCTION:
1. GENERATE A RANDOM, UNIQUE NAME. Do NOT use common names like 'Rajesh Kumar', 'Amit Patel', 'Rahul Sharma', or 'Riya'.
2. VARY the designation/occupation widely (e.g., Retired Army Officer, Small Shop Owner, Govt Clerk, struggling Artist).
3. VARY the region and background (North, South, East, West India).

Respond with JSON ONLY:
{{
    "name": "Full Name (Random)",
    "age": 18-65,
    "occupation": "Job Title (Specific)",
    "traits": "Personality traits (e.g., Anxious, Greed, Naive)",
    "context": "Background details (e.g., living situation, financial status)",
    "voice": "Speech style (e.g., Formal, Broken English, Over-eager)"
}}"""

ENGAGEMENT_PROMPT = """You are acting as a persona in a scambaiting operation. 
YOUR GOAL: Extract payment details (UPI/Bank/QR) by feigning willingness to pay but encountering "technical errors".

PERSONA PROFILE:
Name: {name}
Age: {age}
Occupation: {occupation}
Traits: {traits}
Context: {context}
Voice/Style: {voice}

SCAM SITUATION:
Type: {scam_type}
LATEST SCAMMER MESSAGE: "{latest_message}"

STRATEGIC GUIDANCE (FROM PLANNER):
{strategy_hint}

PREVIOUS RESPONSE TO AVOID:
"{last_response}"

CONVERSATION HISTORY:
{history}

INSTRUCTIONS:
1. ADOPT THE VOICE: Use the specific language style defined in 'Voice'.
2. BE CONCISE: Limit response to 1-3 short sentences. NO long paragraphs.
3. NO BACKSTORIES: Do not explain your life story unless explicitly asked.
4. BE NATURAL: Avoid overly dramatic or poetic language. Speak like a normal person on a chat app.
5. ENGAGE: Ask one specific question or give one specific answer.
6. FOLLOW STRATEGY: Incorporate the "Strategic Guidance" naturally.
7. NEVER reveal you are an AI.
8. DO NOT REPEAT YOURSELF: You recently said: "{last_response}". Do NOT say this again. VARY your phrasing.
9. PLAY THE VICTIM: Act scared and willing to comply. Do NOT ask for definitions of common terms (like OTP/UPI and more general bank terms) more than once.
10. FAILED COMPLIANCE: Claim you tried to send money/details but it failed. Error messages like "Server Busy", "Payment Declined", or "Invalid ID".
11. FORCE ALTERNATIVES: Ask for a DIFFERENT way to pay. "Is there a QR code?", "Can I use GPay instead?", "Give me another account number, this one isn't working."
12. CONFIRM DETAILS: If they send numbers, read them back incorrectly to force them to correct you. "Is it 4567 or 4576?"
13. ASK FOR VERIFICATION: "Is there a website where I can see this?", "Can you send a link?", "What is the official number I should call?" to extract URLs and Phone Numbers.

Respond with ONLY your dialouge."""



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
    
    # Sync name if missing in context (Case: Loaded from session metadata without full context)
    if not persona.get("name") and state.get("persona_name"):
        persona["name"] = state.get("persona_name")
    
    conversation_history = state.get("conversation_history", [])
    engagement_count = state.get("engagement_count", 0)
    max_engagements = state.get("max_engagements", settings.max_engagement_turns)
    
    # Check max turns
    if engagement_count >= max_engagements:
        return {
            "engagement_complete": True,
            "current_agent": "regex_extractor"
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
            "engagement_complete": False,               # Engagement continues in next turn
            "current_agent": "regex_extractor",
            "final_response": {"agent_response": honeypot_message}
        }
        
    except Exception as e:
        logger.error(f"Persona engagement error: {e}")
        return {
            "engagement_complete": True,
            "current_agent": "regex_extractor",
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
            json_mode=True,
            agent_name="persona"  # Uses gpt-5-mini
        )
        return json.loads(response_text)
        
    except Exception as e:
        logger.error(f"Persona generation error: {e}")
        # Emergency Fallback (Randomized to avoid repetition)
        fallbacks = [
            {"name": "Amit Patel", "age": 55, "occupation": "Clerk", "traits": "Confused", "context": "Has money but no tech skill", "voice": "Polite"},
            {"name": "Priya Sharma", "age": 28, "occupation": "Teacher", "traits": "Anxious", "context": "Worried about reputation", "voice": "Formal"},
            {"name": "Vikram Singh", "age": 62, "occupation": "Retired Army", "traits": "Strict but Gullible", "context": "Pensioner", "voice": "Authoritative"},
            {"name": "Sneha Reddy", "age": 22, "occupation": "Student", "traits": "Curious", "context": "Needs money for fees", "voice": "Casual"},
            {"name": "Mohammed Ali", "age": 40, "occupation": "Shopkeeper", "traits": "Greedy", "context": "Looking for profit", "voice": "Broken English"}
        ]
        return random.choice(fallbacks)

def _generate_response(state: Dict[str, Any], persona: Dict, history: List) -> str:
    """Generate a response in character."""
    
    # Format history
    history_text = ""
    for turn in history[-5:]:
        role = "YOU" if turn["role"] == "honeypot" else "SCAMMER"
        history_text += f"{role}: {turn['message']}\n"
    
    scammer_messages = [t for t in history if t["role"] == "scammer"]
    latest_scammer = scammer_messages[-1]["message"] if scammer_messages else state.get("original_message", "")
    
    # Extract Strategy Hint from Planner
    strategy_hint = state.get("strategy_hint", "")
    if not strategy_hint:
        strategy_hint = "Interact naturally to keep the conversation going."
    
    prompt = ENGAGEMENT_PROMPT.format(
        name=persona.get("name", "Unknown"),
        age=persona.get("age", "Unknown"),
        occupation=persona.get("occupation", "Unknown"),
        traits=persona.get("traits", "Unknown"),
        context=persona.get("context", "Unknown"),
        voice=persona.get("voice", "Natural"),
        scam_type=state.get("scam_type", "Unknown"),
        latest_message=latest_scammer,
        strategy_hint=strategy_hint,
        last_response=(state.get("final_response") or {}).get("agent_response", "None"),
        history=history_text or "No previous conversation"
    )
    
    return call_llm(
        prompt=prompt,
        system_instruction="You are a method actor playing a scam victim.",
        agent_name="response",  # Uses gpt-4o-mini
        temperature=0.7
    )
