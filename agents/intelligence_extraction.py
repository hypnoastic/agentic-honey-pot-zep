"""
Intelligence Extraction Agent — UPGRADED PIPELINE
Fixes:
  1. Scans FULL conversation history (not just latest message)
  2. Extracts all 8 entity types required by scoring rubric
  3. Set-based deduplication eliminates duplicate values
  4. Hardened anti-hallucination via LLM verification
"""

import re
import logging
import json
from typing import Dict, Any, List

from config import get_settings
from utils.parsing import parse_json_safely
from utils.prefilter import (
    extract_entities_deterministic,
    filter_low_confidence,
)
from agents.entity_utils import merge_entities, normalize_entity_value, disambiguate_entities
from utils.llm_client import call_llm_async

settings = get_settings()
logger = logging.getLogger(__name__)


# =============================================================================
# ALL 8 ENTITY TYPES  (must match scoring rubric)
# =============================================================================

EXPECTED_ENTITY_KEYS = {
    "upi_ids",
    "bank_accounts",
    "phone_numbers",
    "phishing_urls",
    "ifsc_codes",
    "email_addresses",
    "case_ids",
    "policy_numbers",
    "order_numbers",
}


LLM_VERIFY_PROMPT = """
You are a STRICT intelligence verification system for a scam-detection honeypot.

FULL CONVERSATION TEXT:
{conversation}

REGEX-DETECTED ENTITIES:
{regex_entities}

RULES:
- Only validate entities that are PRESENT (or lightly obfuscated) in the text above.
- Recover obfuscated entities ONLY if they are clearly reconstructable from the text.
- NEVER invent or guess values not in the text.
- NEVER hallucinate digits or characters.
- Confidence: 1.0=exact match, 0.8-0.9=clear obfuscation, 0.6-0.7=weak, <0.6=discard

Entity types to check (all 8):
upi_ids, bank_accounts, phone_numbers, phishing_urls, email_addresses,
case_ids, policy_numbers, order_numbers

Return ONLY valid JSON (no prose, no markdown):
{{
  "verified_entities": {{
    "upi_ids": [],
    "bank_accounts": [],
    "phone_numbers": [],
    "phishing_urls": [],
    "email_addresses": [],
    "case_ids": [],
    "policy_numbers": [],
    "order_numbers": []
  }},
  "obfuscation_detected": {{
    "type": "",
    "description": ""
  }}
}}
"""


# =============================================================================
# MAIN AGENT
# =============================================================================

async def intelligence_extraction_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract intelligence using hardened pipeline.
    Scans FULL conversation history for maximum extraction coverage.
    """

    conversation_history = state.get("conversation_history", [])

    # ── Build full scammer text corpus ────────────────────────────────────────
    # Extract from ALL scammer turns, not just the latest message
    scammer_turns = [
        t["message"] for t in conversation_history
        if t.get("role") == "scammer" and t.get("message")
    ]
    # Also include the original incoming message (sometimes not in history yet)
    original = state.get("original_message", "")
    if original and original not in scammer_turns:
        scammer_turns.append(original)

    if not scammer_turns:
        return {"current_agent": "planner"}

    full_corpus = "\n".join(scammer_turns)

    # ── STEP 1: Deterministic Regex on FULL corpus ────────────────────────────
    new_regex_entities = extract_entities_deterministic(full_corpus)

    # Also run on initial prefilter entities if first turn
    if len(conversation_history) <= 1:
        prefilter_entities = state.get("prefilter_entities", {})
        if prefilter_entities:
            new_regex_entities = merge_entities(new_regex_entities, prefilter_entities)

    # ── STEP 2: LLM Verification ──────────────────────────────────────────────
    try:
        # Use a capped window (last 6 turns) to avoid token overflow
        window = conversation_history[-6:]
        combined_text = "\n".join(
            t["message"].replace("{", "").replace("}", "")[:600]
            for t in window
            if t.get("message")
        )
        # Always include original message
        if original and original not in combined_text:
            combined_text = original + "\n" + combined_text

        prompt = LLM_VERIFY_PROMPT.format(
            conversation=combined_text[:3000],
            regex_entities=_format_entities_for_prompt(new_regex_entities)
        )

        response_text = await call_llm_async(
            prompt=prompt,
            system_instruction="Verify and recover entities strictly from the conversation. Return JSON only.",
            json_mode=True,
            agent_name="extraction",
        )

        llm_result = parse_json_safely(response_text) or {}
        new_llm_entities = llm_result.get("verified_entities", {})

        # Schema enforcement — only allow known entity types
        new_llm_entities = _enforce_schema(new_llm_entities)

        # Anti-hallucination: validate every LLM entity is actually in the text
        new_llm_entities = _validate_llm_output_against_text(
            new_llm_entities, full_corpus + "\n" + combined_text
        )

        combined_new_entities = merge_entities(new_regex_entities, new_llm_entities)

    except Exception as e:
        logger.warning(f"LLM verification failed: {e}")
        combined_new_entities = new_regex_entities

    # ── STEP 3: Normalize + Confidence Filter ────────────────────────────────
    combined_new_entities = _normalize_entities(combined_new_entities)
    combined_new_entities = filter_low_confidence(combined_new_entities, threshold=0.6)

    # ── STEP 4: Merge with Prior Entities ────────────────────────────────────
    existing_entities = state.get("extracted_entities", {}) or {}
    final_entities = merge_entities(existing_entities, combined_new_entities)

    # Schema enforcement — guarantee all 8 keys exist
    final_entities = _enforce_schema(final_entities)

    # ── STEP 5: Set-based Global Deduplication ────────────────────────────────
    final_entities = _deduplicate_all(final_entities)

    from utils.logger import AgentLogger
    merged_details = (
        f"Prior={_count_entities(existing_entities)}, "
        f"New={_count_entities(combined_new_entities)}, "
        f"Final={_count_entities(final_entities)}"
    )
    AgentLogger._print_colored("INTELLIGENCE", "yellow", "📊", "Entity Merge", merged_details)

    return {
        "extracted_entities": final_entities,
        "current_agent": "intelligence_extraction"
    }


def _count_entities(entities: Dict) -> int:
    total = 0
    for v in entities.values():
        if isinstance(v, list):
            total += len(v)
    return total


# =============================================================================
# HARDENING UTILITIES
# =============================================================================

def _enforce_schema(entities: Dict) -> Dict:
    """Ensure all 8 entity types are present (with empty lists as default)."""
    return {key: entities.get(key, []) for key in EXPECTED_ENTITY_KEYS}


def _deduplicate_all(entities: Dict) -> Dict:
    """
    Global deduplication across all entity types.
    Removes duplicate values (case-insensitive comparison for strings).
    Preserves the first (highest-confidence) occurrence.
    """
    deduped = {}
    for entity_type, items in entities.items():
        seen = set()
        clean = []
        for item in items:
            if isinstance(item, dict):
                val = str(item.get("value", "")).strip().lower()
                raw = item
            else:
                val = str(item).strip().lower()
                raw = item
            if val and val not in seen:
                seen.add(val)
                clean.append(raw)
        deduped[entity_type] = clean
    return deduped


def _validate_llm_output_against_text(
    llm_entities: Dict,
    source_text: str
) -> Dict:
    """
    Anti-hallucination: every entity must be findable (or lightly normalized)
    in the source text.
    """
    validated = {}
    normalized_source = source_text.replace(" ", "").lower()
    normalized_source = normalized_source.replace("o", "0")

    for entity_type, items in llm_entities.items():
        validated[entity_type] = []
        for item in items:
            if isinstance(item, str):
                value = item
            else:
                value = str(item.get("value", ""))
            if not value:
                continue
            normalized_value = value.replace(" ", "").lower()
            if (
                normalized_value in normalized_source
                or normalized_value.replace("0", "o") in normalized_source
            ):
                validated[entity_type].append(item)
    return validated


def _normalize_entities(entities: Dict) -> Dict:
    """Canonical normalization using entity_utils."""
    normalized = {}
    for key, items in entities.items():
        normalized[key] = []
        for item in items:
            if isinstance(item, dict):
                raw_val = item.get("value", "")
                norm_val = normalize_entity_value(raw_val, key)
                item["value"] = norm_val
                normalized[key].append(item)
    return disambiguate_entities(normalized)


def _format_entities_for_prompt(entities: Dict) -> str:
    """Format entities dict for LLM prompt."""
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
    Fast, deterministic extraction using REGEX ONLY on FULL conversation history.
    Used during the engagement loop to minimize latency.
    """
    from utils.prefilter import extract_entities_deterministic

    conversation_history = state.get("conversation_history", [])

    # Collect ALL scammer turns
    scammer_texts = [
        t["message"] for t in conversation_history
        if t.get("role") == "scammer" and t.get("message")
    ]
    original = state.get("original_message", "")
    if original and original not in scammer_texts:
        scammer_texts.append(original)

    if not scammer_texts:
        return {"current_agent": "response_formatter"}

    full_corpus = "\n".join(scammer_texts)

    # Run deterministic extraction on full corpus
    regex_entities = extract_entities_deterministic(full_corpus)

    # Enforce all 8 entity keys
    regex_entities = _enforce_schema(regex_entities)

    # Merge with existing
    current_entities = _enforce_schema(state.get("extracted_entities", {}) or {})
    final_entities = merge_entities(current_entities, regex_entities)
    final_entities = _enforce_schema(final_entities)
    final_entities = _deduplicate_all(final_entities)

    return {
        "extracted_entities": final_entities,
        "current_agent": "response_formatter"
    }
