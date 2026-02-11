"""
Intelligence Extraction Agent
HARDENED PIPELINE:
Deterministic Regex → LLM Verification → Re-validation → Normalization → Safe Merge

Security Guarantees:
- LLM cannot invent entities (post-validation enforced)
- All outputs validated against source text
- Confidence-based per-turn filtering
- Canonical normalization before merge
- Deduplicated + confidence-prioritized merging
"""

import re
import logging
from typing import Dict, Any, List

from config import get_settings
from utils.parsing import parse_json_safely
from utils.prefilter import (
    extract_entities_deterministic,
    merge_entities,
    filter_low_confidence,
)

settings = get_settings()
logger = logging.getLogger(__name__)


# =============================================================================
# STRICT LLM PROMPT (HARDENED)
# =============================================================================

LLM_VERIFY_PROMPT = """
You are a STRICT intelligence verification system.

You MUST:
- Only validate entities present in the text.
- Recover obfuscated entities ONLY if reconstructable from the text.
- NEVER invent new values.
- NEVER guess missing digits.

If an entity cannot be directly found or reconstructed from the conversation,
DO NOT include it.

Confidence rules:
1.0 = Exact literal match
0.8-0.9 = Recovered from clear obfuscation
0.6-0.7 = Weak reconstruction
<0.6 = Discard

Entity types allowed:
upi_ids, bank_accounts, phone_numbers, phishing_urls, ifsc_codes

Return ONLY valid JSON:
{{
  "verified_entities": {{
    "upi_ids": [],
    "bank_accounts": [],
    "phone_numbers": [],
    "phishing_urls": [],
    "ifsc_codes": []
  }},
  "obfuscation_detected": {{
    "type": "",
    "description": ""
  }}
}}
"""


EXPECTED_ENTITY_KEYS = {
    "upi_ids",
    "bank_accounts",
    "phone_numbers",
    "phishing_urls",
    "ifsc_codes",
}


# =============================================================================
# MAIN AGENT
# =============================================================================

async def intelligence_extraction_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract intelligence using hardened pipeline.
    """

    conversation_history = state.get("conversation_history", [])

    scammer_messages = [t for t in conversation_history if t["role"] == "scammer"]
    latest_text = (
        scammer_messages[-1]["message"]
        if scammer_messages
        else state.get("original_message", "")
    )

    if not latest_text:
        return {"current_agent": "planner"}

    # -------------------------------------------------------------------------
    # STEP 1: Deterministic Regex Extraction (Latest Only)
    # -------------------------------------------------------------------------

    new_regex_entities = extract_entities_deterministic(latest_text)

    if len(conversation_history) <= 1:
        prefilter_entities = state.get("prefilter_entities", {})
        if prefilter_entities:
            new_regex_entities = merge_entities(
                new_regex_entities, prefilter_entities
            )

    # -------------------------------------------------------------------------
    # STEP 2: LLM Verification (Context Window for Obfuscation Recovery)
    # -------------------------------------------------------------------------

    try:
        conversation_window = conversation_history[-3:]
        combined_text = "\n".join(t["message"] for t in conversation_window)

        prompt = LLM_VERIFY_PROMPT.format(
            conversation=combined_text,
            regex_entities=_format_entities_for_prompt(new_regex_entities)
        )

        from utils.llm_client import call_llm_async

        response_text = await call_llm_async(
            prompt=prompt,
            system_instruction="Verify and recover entities strictly from text.",
            json_mode=True,
            agent_name="extraction",
        )

        llm_result = parse_json_safely(response_text) or {}
        new_llm_entities = llm_result.get("verified_entities", {})
        
        # Schema enforcement
        new_llm_entities = _enforce_schema(new_llm_entities)

        # Re-validate against text (anti-hallucination guarantee)
        new_llm_entities = _validate_llm_output_against_text(
            new_llm_entities, combined_text
        )

        combined_new_entities = merge_entities(
            new_regex_entities, new_llm_entities
        )

    except Exception as e:
        logger.warning(f"LLM verification failed: {e}")
        combined_new_entities = new_regex_entities

    # -------------------------------------------------------------------------
    # STEP 3: Normalize + Per-turn Confidence Filter
    # -------------------------------------------------------------------------

    combined_new_entities = _normalize_entities(combined_new_entities)
    combined_new_entities = filter_low_confidence(
        combined_new_entities, threshold=0.6
    )

    # -------------------------------------------------------------------------
    # STEP 4: Safe Incremental Merge into Global State
    # -------------------------------------------------------------------------

    existing_entities = state.get("extracted_entities", {}) or {}
    final_entities = _safe_confidence_merge(
        existing_entities, combined_new_entities
    )

    return {
        "extracted_entities": final_entities,
        "current_agent": "planner",
    }


# =============================================================================
# HARDENING UTILITIES
# =============================================================================

def _enforce_schema(entities: Dict) -> Dict:
    """Remove unknown entity types."""
    return {
        key: entities.get(key, [])
        for key in EXPECTED_ENTITY_KEYS
    }


def _validate_llm_output_against_text(
    llm_entities: Dict,
    source_text: str
) -> Dict:
    """
    Ensure every returned entity is present or reconstructable
    from source text.
    """

    validated = {}

    normalized_source = source_text.replace(" ", "").lower()
    # Support common substitutions in source for validation
    normalized_source = normalized_source.replace("o", "0")

    for entity_type, items in llm_entities.items():
        validated[entity_type] = []

        for item in items:
            value = str(item.get("value", ""))
            if not value:
                continue

            normalized_value = value.replace(" ", "").lower()
            # If the value is '9876543210', it matches against '9876543210' (where original was '...1o')
            if normalized_value in normalized_source:
                validated[entity_type].append(item)
            elif normalized_value.replace("0", "o") in normalized_source:
                validated[entity_type].append(item)

    return validated


def _normalize_entities(entities: Dict) -> Dict:
    """Canonical normalization layer."""
    normalized = {}

    for key, items in entities.items():
        normalized[key] = []

        for item in items:
            if isinstance(item, dict):
                value = item.get("value", "").strip()
                value = re.sub(r"\s+", "", value)

                if key == "upi_ids":
                    value = value.lower()

                item["value"] = value
                normalized[key].append(item)

    return normalized


def _safe_confidence_merge(existing: Dict, new: Dict) -> Dict:
    """
    Merge with confidence prioritization.
    Keeps highest-confidence version of duplicates.
    """

    merged = existing.copy()

    for entity_type, items in new.items():
        if entity_type not in merged:
            merged[entity_type] = []

        existing_map = {
            e["value"]: e for e in merged[entity_type]
        }

        for item in items:
            value = item["value"]
            new_conf = item.get("confidence", 0)

            if value in existing_map:
                if new_conf > existing_map[value].get("confidence", 0):
                    existing_map[value] = item
            else:
                existing_map[value] = item

        merged[entity_type] = list(existing_map.values())

    return merged


def _format_entities_for_prompt(entities: Dict) -> str:
    """Format entities for LLM prompt."""
    lines = []
    for entity_type, items in entities.items():
        if items:
            values = []
            for item in items:
                if isinstance(item, dict):
                    values.append(item.get("value", str(item)))
                else:
                    values.append(str(item))
            if values:
                lines.append(f"- {entity_type}: {', '.join(values[:5])}")

    return "\n".join(lines) if lines else "None extracted"

def regex_only_extraction_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fast, deterministic extraction using REGEX ONLY.
    Used during the engagement loop to minimize latency.
    """
    from utils.prefilter import extract_entities_deterministic, merge_entities
    
    conversation_history = state.get("conversation_history", [])
    scammer_messages = [t for t in conversation_history if t["role"] == "scammer"]
    latest_text = (
        scammer_messages[-1]["message"]
        if scammer_messages
        else state.get("original_message", "")
    )
    
    if not latest_text:
        return {"current_agent": "response_formatter"}
            
    # Run deterministic extraction
    regex_entities = extract_entities_deterministic(latest_text)
    
    # Merge with existing entities
    current_entities = state.get("extracted_entities", {}) or {}
    final_entities = merge_entities(current_entities, regex_entities)
    
    return {
        "extracted_entities": final_entities,
        "current_agent": "response_formatter"
    }
