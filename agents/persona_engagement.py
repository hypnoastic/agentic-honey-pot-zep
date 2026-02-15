"""
Persona Engagement Agent (Production Grade - Final - Fixed)

Fixes:
- Prevents repeated persona across sessions
- Injects entropy using conversation_id
- Higher temperature ONLY for persona generation
- Engagement remains deterministic
"""

import json
import random
import logging
import uuid
from typing import Dict, Any, List
from utils.llm_client import call_llm_async
from config import get_settings
from utils.parsing import parse_json_safely

settings = get_settings()
logger = logging.getLogger(__name__)


# =========================================================
# PERSONA GENERATION PROMPT
# =========================================================

PERSONA_GENERATION_PROMPT = """Create a UNIQUE and uncommon Indian persona.

Entropy Seed: {entropy_seed}

Context: "{message}" ({scam_type})
Traits Instruction: {traits_instruction}

RULES:
- Avoid common names (Rajesh, Rahul, Amit, Priya, etc.)
- Ensure regionally realistic naming
- Occupation must be specific
- Background must be 1 short sentence
- Keep output minimal
- NEVER repeat identities from similar prompts

Return JSON ONLY:
{{
  "name": "Full Name",
  "age": 18-65,
  "occupation": "Specific job",
  "traits": "Key personality traits",
  "context": "1-line background",
  "voice": "Speech style"
}}
"""


# =========================================================
# ENGAGEMENT PROMPT (UNCHANGED)
# =========================================================

ENGAGEMENT_PROMPT = """You are a real human (NOT an AI).

GOAL:
Engage naturally. Follow the PLANNER STRATEGY below to decide whether to stall, feign ignorance, or ask for details.

PROFILE:
{name} | {occupation} | {traits} | {voice}

SCAM TYPE:
{scam_type}

FULL CONVERSATION HISTORY (oldest → newest):
{chat_context}

👉 PLANNER STRATEGY (FOLLOW THIS):
{strategy_hint}

GUIDELINES:
1. **Context is King**: Read the FULL history. If you already asked for something, don't ask again immediately. If the scammer explained something, acknowledge it.
2. **Be Human**: You can be confused, worried, busy, or skeptical. Vary your tone based on your Persona.
3. **No Robot Rules**: You don't have to ask a question every time. You can make statements too.
4. **Stalling**: If the strategy says STALL, asking for clarification, official links, or employee IDs are good tactics.
5. **Extraction**: If the strategy says EXTRACT, ask specifically for the missing info (Account, UPI, Link) in a way that fits the conversation.
7. **Brevity & Engagement**: Keep responses SHORT (1-2 lines). BUT, you MUST end with a question or a request for the next step to keep them talking. Don't just say "Okay".
8. **Safety**: NEVER reveal you are an AI or Honeypot.

Respond with the next natural message in the dialogue.
"""


# =========================================================
# MAIN AGENT
# =========================================================

async def persona_engagement_agent(state: Dict[str, Any]) -> Dict[str, Any]:

    if not state.get("persona_name"):
        persona = await _generate_unique_persona(state)
        state["persona_name"] = persona["name"]
        state["persona_context"] = json.dumps(persona)

        from utils.logger import AgentLogger
        AgentLogger.persona_update(
            persona["name"],
            persona["occupation"],
            "Persona Generated"
        )

    persona_context = state.get("persona_context", "{}")
    persona = json.loads(persona_context)

    conversation_history = state.get("conversation_history", [])
    engagement_count = state.get("engagement_count", 0)
    max_engagements = min(10, state.get("max_engagements", settings.max_engagement_turns))

    if engagement_count >= max_engagements:
        return {
            "engagement_complete": True,
            "current_agent": "regex_extractor"
        }

    try:
        honeypot_message = await _generate_response(state, persona, conversation_history)

        from utils.logger import AgentLogger
        AgentLogger.response_generated(honeypot_message)

        new_history = list(conversation_history)
        new_history.append({
            "role": "honeypot",
            "message": honeypot_message,
            "turn_number": engagement_count + 1
        })

        return {
            "persona_name": persona.get("name"),
            "persona_context": json.dumps(persona),
            "conversation_history": new_history,
            "engagement_count": engagement_count + 1,
            "engagement_complete": False,
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


# =========================================================
# PERSONA GENERATION (FIXED)
# =========================================================

async def _generate_unique_persona(state: Dict[str, Any]) -> Dict:

    message = state.get("original_message", "")
    scam_type = state.get("scam_type", "Unknown")

    # 🔥 Controlled entropy using conversation_id
    conversation_id = state.get("conversation_id", str(uuid.uuid4()))
    entropy_seed = conversation_id[-8:]  # stable per session

    traits = state.get("persona_traits", {})
    if traits:
        safe_traits = {
            k: v for k, v in traits.items()
            if k not in ["name", "age", "occupation", "context", "voice"]
        }
        traits_instruction = ", ".join([f"{k}: {v}" for k, v in safe_traits.items()]) \
            if safe_traits else "Choose traits matching scam context."
    else:
        traits_instruction = "Choose traits matching scam context."

    prompt = PERSONA_GENERATION_PROMPT.format(
        message=message,
        scam_type=scam_type,
        traits_instruction=traits_instruction,
        entropy_seed=entropy_seed
    )

    try:
        # 🔥 Higher temperature ONLY for persona
        response_text = await call_llm_async(
            prompt=prompt,
            system_instruction="Generate fictional character profile.",
            json_mode=True,
            agent_name="persona",
            temperature=0.9  # increased randomness
        )

        persona = parse_json_safely(response_text)

        if isinstance(persona, list) and persona:
            persona = persona[0]

        if not isinstance(persona, dict):
            raise ValueError("Invalid persona format")

        return persona

    except Exception as e:
        logger.error(f"Persona generation error: {e}")

        fallbacks = [
            {"name": "Harbhajan Lakhotia", "age": 53, "occupation": "Municipal tax clerk",
             "traits": "Technically confused", "context": "Lives in Jaipur suburb",
             "voice": "Formal Hindi-English"},
            {"name": "Lhingneilam Pamei", "age": 29, "occupation": "Nurse trainee",
             "traits": "Anxious but cooperative", "context": "Renting in Guwahati",
             "voice": "Soft English"},
            {"name": "Chandraketu Pradhan", "age": 61, "occupation": "Retired railway supervisor",
             "traits": "Slow and trusting", "context": "Pension dependent",
             "voice": "Polite"},
            {"name": "Samarjit Boro", "age": 34, "occupation": "Freelance electrician",
             "traits": "Practical but impatient", "context": "Contract worker",
             "voice": "Direct"}
        ]

        # Deterministic fallback selection based on UUID
        index = int(uuid.UUID(conversation_id)) % len(fallbacks)
        return fallbacks[index]


# =========================================================
# RESPONSE GENERATION (UNCHANGED)
# =========================================================

async def _generate_response(state: Dict[str, Any], persona: Dict, history: List) -> str:

    # Use FULL history (up to reasonable limit, e.g., last 20 turns to fit context)
    # The Planner sees everything, but Persona needs context to sound natural.
    # We'll take the last 20 messages to ensure we don't hit token limits on very long chats,
    # but 20 is effectively "full" for this use case (10 user + 10 agent turns).
    full_history = history[-20:] 

    context_lines = []
    for turn in full_history:
        role_label = "SCAMMER" if turn["role"] == "scammer" else "YOU"
        sanitized_msg = turn['message'].replace('{', '').replace('}', '')[:500]
        context_lines.append(f"{role_label}: {sanitized_msg}")

    chat_context = "\n".join(context_lines) if context_lines else "No previous conversation."
    strategy_hint = state.get("strategy_hint", "Engage naturally and extract details.")

    prompt = ENGAGEMENT_PROMPT.format(
        name=persona.get("name", "Unknown"),
        occupation=persona.get("occupation", "Unknown"),
        traits=persona.get("traits", "Normal"),
        voice=persona.get("voice", "Natural"),
        scam_type=state.get("scam_type", "Unknown"),
        chat_context=chat_context,
        strategy_hint=strategy_hint
    )

    return await call_llm_async(
        prompt=prompt,
        system_instruction="You are a real human victim. Respond naturally based on the full conversation history.",
        agent_name="response",
        temperature=0.6 # Slightly higher for more natural, less robotic responses
    )
