"""
Persona Engagement Agent (Production Grade - Final)

- Gemini Flash Optimized
- Deterministic + Low Token
- Extraction-focused (3–4 turns ideal)
- Hard cap: 10 turns
- Injects last 6 turns in chronological order
- Anti-repetition guard
- One-question-per-turn enforcement
"""

import json
import random
import logging
from typing import Dict, Any, List
from utils.llm_client import call_llm_async
from config import get_settings
from utils.parsing import parse_json_safely

settings = get_settings()
logger = logging.getLogger(__name__)


# =========================================================
# PERSONA GENERATION PROMPT (Minimal + Strict)
# =========================================================

PERSONA_GENERATION_PROMPT = """Create a UNIQUE and uncommon Indian persona.

Context: "{message}" ({scam_type})
Traits Instruction: {traits_instruction}

RULES:
- Avoid common names (Rajesh, Rahul, Amit, Priya, etc.)
- Ensure regionally realistic naming
- Occupation must be specific
- Background must be 1 short sentence
- Keep output minimal

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
# ENGAGEMENT PROMPT (Chronological Context Injection)
# =========================================================

ENGAGEMENT_PROMPT = """You are a real human (NOT an AI).

GOAL:
Extract actionable identifiers (UPI, Bank Account, URL, Phone) within 3-4 turns.

PROFILE:
{name} | {occupation} | {traits} | {voice}

SCAM TYPE:
{scam_type}

RECENT CHAT (oldest → newest):
{chat_context}

PLANNER STRATEGY:
{strategy_hint}

STRICT RULES:
1. Reply directly to the LAST message in context.
2. Ask ONLY ONE actionable question.
3. Maximum 2 short sentences. Max 30 words.
4. NEVER accuse, threaten, expose scam, or mention AI.
5. Do NOT repeat tone or structure from your earlier replies.
6. If payment mentioned → ask for UPI or bank details.
7. If verification mentioned → ask for official website link.
8. Never ask for QR codes.
9. No moral lectures.

Respond with natural dialogue only.
"""


# =========================================================
# MAIN AGENT
# =========================================================

async def persona_engagement_agent(state: Dict[str, Any]) -> Dict[str, Any]:

    # -----------------------------
    # Persona Initialization
    # -----------------------------
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
    
    # Load existing persona (skip LLM if already valid)
    persona_context = state.get("persona_context", "{}")
    if persona_context and persona_context != "{}":
        persona = json.loads(persona_context)
    else:
        # Fallback: generate if somehow missing
        persona = await _generate_unique_persona(state)
        state["persona_context"] = json.dumps(persona)

    conversation_history = state.get("conversation_history", [])
    engagement_count = state.get("engagement_count", 0)
    max_engagements = min(10, state.get("max_engagements", settings.max_engagement_turns))

    # Hard cap
    if engagement_count >= max_engagements:
        return {
            "engagement_complete": True,
            "current_agent": "regex_extractor"
        }

    try:
        honeypot_message = await _generate_response(state, persona, conversation_history)

        from utils.logger import AgentLogger
        AgentLogger.response_generated(honeypot_message)

        # Update history
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
# PERSONA GENERATION
# =========================================================

async def _generate_unique_persona(state: Dict[str, Any]) -> Dict:

    message = state.get("original_message", "")
    scam_type = state.get("scam_type", "Unknown")

    traits = state.get("persona_traits", {})
    if traits:
        # Filter out identity-specific fields to force unique generation
        # We only want behavioral traits (e.g., "Anxious", "Skeptical")
        safe_traits = {k: v for k, v in traits.items() if k not in ["name", "age", "occupation", "context", "voice"]}
        if safe_traits:
            traits_instruction = ", ".join([f"{k}: {v}" for k, v in safe_traits.items()])
        else:
            traits_instruction = "Choose traits matching scam context. ensure UNIQUE identity."
    else:
        traits_instruction = "Choose traits matching scam context."

    prompt = PERSONA_GENERATION_PROMPT.format(
        message=message,
        scam_type=scam_type,
        traits_instruction=traits_instruction
    )

    try:
        response_text = await call_llm_async(
            prompt=prompt,
            system_instruction="Generate fictional character profile.",
            json_mode=True,
            agent_name="persona"
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

        return random.choice(fallbacks)


# =========================================================
# RESPONSE GENERATION (ORDER-PRESERVING CONTEXT)
# =========================================================

async def _generate_response(state: Dict[str, Any], persona: Dict, history: List) -> str:

    # 1. Get last 6 turns preserving chronological order (sanitized)
    recent_history = history[-6:]

    context_lines = []
    for turn in recent_history:
        role_label = "SCAMMER" if turn["role"] == "scammer" else "YOU"
        # Sanitize message to prevent prompt injection
        sanitized_msg = turn['message'].replace('{', '').replace('}', '')[:300]
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

    # 2. Force model to respond to last message only
    return await call_llm_async(
        prompt=prompt,
        system_instruction="You are a real human victim. Reply directly to the very last message in the context.",
        agent_name="response",
        temperature=0.45
    )
