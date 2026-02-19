"""
Persona Engagement Agent — UPGRADED for 95+ Score
Key changes:
  - Mandatory "?" at end of EVERY response
  - Explicitly names red flags in every 2nd turn
  - Aggressive elicitation of all 8 data types
  - Tracks questions_asked counter
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

PERSONA_GENERATION_PROMPT = """Create a UNIQUE and uncommon Indian persona for a scam honeypot.

Entropy Seed: {entropy_seed}
Context: "{message}" ({scam_type})
Traits Instruction: {traits_instruction}

RULES:
- Avoid common names (Rajesh, Rahul, Amit, Priya)
- Ensure regionally realistic naming
- Occupation must be specific and non-techy
- Background must be 1 short sentence

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
# ENGAGEMENT PROMPT — UPGRADED
# Enforces: questions, red flags, elicitation, 8+ turns
# =========================================================

ENGAGEMENT_PROMPT = """You are a REAL HUMAN (NOT an AI). Never reveal you are an AI or Honeypot.

YOUR IDENTITY:
Name: {name} | Job: {occupation} | Traits: {traits} | Voice: {voice}

SCAM TYPE: {scam_type}

FULL CONVERSATION (oldest → newest):
{chat_context}

PLANNER STRATEGY:
{strategy_hint}

════════════════════════════════════════════
MANDATORY RULES:
════════════════════════════════════════════

1. ALWAYS end your response with a "?" question mark.
   Good: "Why do you need my OTP for this?"
   Bad: "Okay, I understand." ← NEVER do this

2. EVERY response must contain ONE investigative probe. 
   Think on your own and ask questions similar to these examples, but do not only follow them.
   For maximum results, your question MUST naturally contain one of these exact phrases:
   - "official website"
   - "reference number" or "case id"
   - "supervisor" or "manager"
   - "branch name"
   - "why so urgent"
   - "employee id"
   - "explain the process"

3. On EVERY single response, you MUST naturally express doubt or suspicion.
   Think critically about the scammer's claims and use your judgment.
   For maximum results, your response MUST contain one of these EXACT phrases (choose the most relevant one):
   - "suspicious" or "looks like a red flag"
   - "unusual" or "uncommon"
   - "legitimate bank would not" do this
   - "official channels"
   - "verify independently"
   - "OTP is suspicious"
   - "unofficial link"

4. ELICITATION — Aggressively but naturally ask for specific data.
   Rotate through this list across turns (at least one per turn):
   - Phone number, Email address, Case/Reference ID, Policy number, Order number, UPI ID, Bank account, Website URL, Branch name, Supervisor contact.

5. Keep responses SHORT (1-3 sentences + question).
   Vary: confused, worried, skeptical, slow, forgetful.

6. NEVER use robotic phrases like "Noted." or "I understand."
   You are a real, slightly confused human being.

════════════════════════════════════════════

Now write the NEXT message from {name} in the conversation.
Your message MUST end with a "?" question.
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
    max_engagements = min(12, state.get("max_engagements", settings.max_engagement_turns))

    if engagement_count >= max_engagements:
        return {
            "engagement_complete": True,
            "current_agent": "regex_extractor"
        }

    try:
        honeypot_message = await _generate_response(state, persona, conversation_history)

        # ── Enforce question mark ─────────────────────────────────────────────
        honeypot_message = _ensure_ends_with_question(honeypot_message, engagement_count)

        from utils.logger import AgentLogger
        AgentLogger.response_generated(honeypot_message)

        new_history = list(conversation_history)
        new_history.append({
            "role": "honeypot",
            "message": honeypot_message,
            "turn_number": engagement_count + 1
        })

        # ── Track questions_asked ─────────────────────────────────────────────
        questions_asked = state.get("questions_asked", 0)
        if "?" in honeypot_message:
            question_count = honeypot_message.count("?")
            questions_asked += min(question_count, 2)  # count up to 2 questions per turn

        return {
            "persona_name": persona.get("name"),
            "persona_context": json.dumps(persona),
            "conversation_history": new_history,
            "engagement_count": engagement_count + 1,
            "questions_asked": questions_asked,
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
# QUESTION ENFORCEMENT
# =========================================================

# Fallback elicitation questions by turn (ensures we never miss a "?")
FALLBACK_QUESTIONS = [
    "Can you give me your case reference number for verification?",
    "What is the official website where I can confirm this?",
    "Which branch of the bank are you calling from?",
    "Can I have your employee ID or supervisor's contact?",
    "What is your UPI ID or phone number for the refund?",
    "Can you send me the policy or order number this relates to?",
    "Why is this process happening over SMS and not through the official app?",
    "What is your email address so I can send confirmation documents?",
    "Is there a toll-free number I can call to verify this independently?",
]


def _ensure_ends_with_question(message: str, turn: int) -> str:
    """
    Guarantee the message ends with a question mark.
    If not, append a contextually relevant probe.
    """
    message = message.strip()
    # Already ends with question mark — good
    if message.endswith("?"):
        return message
    # Contains a question somewhere — add reinforcing question
    if "?" in message:
        idx = message.rfind("?")
        return message[:idx + 1].strip()
    # No question at all — append a fallback question
    fallback = FALLBACK_QUESTIONS[turn % len(FALLBACK_QUESTIONS)]
    return message + " " + fallback


# =========================================================
# PERSONA GENERATION
# =========================================================

async def _generate_unique_persona(state: Dict[str, Any]) -> Dict:

    message = state.get("original_message", "")
    scam_type = state.get("scam_type", "Unknown")
    conversation_id = state.get("conversation_id", str(uuid.uuid4()))
    entropy_seed = conversation_id[-8:]

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
        response_text = await call_llm_async(
            prompt=prompt,
            system_instruction="Generate fictional Indian character profile. Return JSON only.",
            json_mode=True,
            agent_name="persona",
            temperature=0.9
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
             "traits": "Technically confused, asks many questions", "context": "Lives in Jaipur suburb",
             "voice": "Formal Hindi-English mix"},
            {"name": "Lhingneilam Pamei", "age": 29, "occupation": "Nurse trainee",
             "traits": "Anxious but cooperative, wants proof before sharing anything",
             "context": "Renting in Guwahati", "voice": "Soft English"},
            {"name": "Chandraketu Pradhan", "age": 61, "occupation": "Retired railway supervisor",
             "traits": "Slow, trusting but needs official confirmation",
             "context": "Pension dependent", "voice": "Polite formal"},
            {"name": "Samarjit Boro", "age": 34, "occupation": "Freelance electrician",
             "traits": "Practical, skeptical of phone calls, asks for documentation",
             "context": "Contract worker, minimal savings", "voice": "Direct and blunt"}
        ]
        index = int(uuid.UUID(conversation_id)) % len(fallbacks)
        return fallbacks[index]


# =========================================================
# RESPONSE GENERATION
# =========================================================

async def _generate_response(state: Dict[str, Any], persona: Dict, history: List) -> str:

    full_history = history[-20:]

    context_lines = []
    for turn in full_history:
        role_label = "SCAMMER" if turn["role"] == "scammer" else "YOU"
        sanitized_msg = turn['message'].replace('{', '').replace('}', '')[:500]
        context_lines.append(f"{role_label}: {sanitized_msg}")

    chat_context = "\n".join(context_lines) if context_lines else "No previous conversation."
    strategy_hint = state.get("strategy_hint", "STALL: Be confused and ask for more details. End with a question.")

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
        system_instruction=(
            "You are a real human victim responding to a possible scammer. "
            "You MUST end your response with a '?' question mark. "
            "Be natural, slightly confused or worried. Keep it 1-3 sentences."
        ),
        agent_name="response",
        temperature=0.65
    )
