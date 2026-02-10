"""
Intelligence Extraction Agent
HARDENED PIPELINE: Regex extraction → LLM verification → Confidence scoring
Anti-hallucination design: LLM cannot invent entities, only verify/recover obfuscated ones.
"""

import json
import re
import logging
from typing import Dict, Any, List
from utils.llm_client import call_llm
from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


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
        logger.warning(f"JSON parse error: {e}")
        return {}


# LLM VERIFICATION PROMPT - Instructs LLM to VERIFY, not invent
LLM_VERIFY_PROMPT = """You are an intelligence VERIFICATION system. Your job is to VERIFY and RECOVER entities, NOT invent new ones.

CONVERSATION TEXT:
{conversation}

REGEX-EXTRACTED ENTITIES (HIGH CONFIDENCE):
{regex_entities}

YOUR TASK:
1. VERIFY each regex-extracted entity is valid
2. RECOVER any OBFUSCATED entities the regex missed:
   - Spaced digits: "9 8 7 6 5 4 3 2 1 0" → "9876543210"
   - Word numbers: "nine eight seven" → normalize
   - Split across messages: combine fragments
   - Character substitution: "O" for "0", "l" for "1"
   - Hidden in URLs or text
3. DO NOT INVENT entities that are not in the text
4. Assign confidence scores:
   - 1.0 = Explicit, exact match
   - 0.8-0.9 = Obfuscated but recovered
   - 0.6-0.7 = Inferred/uncertain
   - <0.6 = Too uncertain, DISCARD

Entity types to extract:
- upi_ids: xxx@upi, xxx@paytm, xxx@gpay, xxx@ybl, etc.
- bank_accounts: 9-18 digit numbers
- ifsc_codes: XXXX0XXXXXX format
- phone_numbers: Indian mobile (+91, 6/7/8/9xxxxxxxxx)
- phishing_urls: Suspicious URLs

Respond with JSON ONLY:
{{
    "verified_entities": {{
        "upi_ids": [{{"value": "...", "confidence": 0.0-1.0, "source": "explicit|inferred"}}],
        "bank_accounts": [{{"value": "...", "confidence": 0.0-1.0, "source": "explicit|inferred"}}],
        "phone_numbers": [{{"value": "...", "confidence": 0.0-1.0, "source": "explicit|inferred"}}],
        "phishing_urls": [{{"value": "...", "confidence": 0.0-1.0, "source": "explicit|inferred"}}],
        "ifsc_codes": [{{"value": "...", "confidence": 0.0-1.0, "source": "explicit|inferred"}}]
    }},
    "obfuscation_detected": "Description of any obfuscation patterns found"
}}"""


def intelligence_extraction_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract intelligence entities using HARDENED pipeline:
    1. Regex extraction (deterministic, high confidence)
    2. LLM verification (recover obfuscated, assign confidence)
    3. Merge and filter low-confidence entities
    """
    
    conversation_history = state.get("conversation_history", [])
    original_message = state.get("original_message", "")
    
    # Combine all text
    all_text = f"Original message: {original_message}\n\n"
    for turn in conversation_history:
        role = "Honeypot" if turn.get("role") == "honeypot" else "Scammer"
        all_text += f"{role}: {turn.get('message', '')}\n"
        
        revealed = turn.get("revealed_info", {})
        if revealed:
            all_text += f"[Revealed: {json.dumps(revealed)}]\n"
    
    # =========================================================================
    # STEP 1: REGEX EXTRACTION (Deterministic, High Confidence)
    # =========================================================================
    from utils.prefilter import extract_entities_deterministic
    
    regex_entities = extract_entities_deterministic(all_text)
    regex_count = sum(len(v) for v in regex_entities.values())
    
    logger.info(f"EXTRACTION STEP 1: Regex found {regex_count} entities")
    
    # Also use prefilter entities if available (from pre-filter node)
    prefilter_entities = state.get("prefilter_entities", {})
    if prefilter_entities:
        regex_entities = _merge_entity_dicts(regex_entities, prefilter_entities)
    
    # =========================================================================
    # STEP 2: LLM VERIFICATION (Only if needed)
    # =========================================================================
    # Skip LLM if we already have plenty of entities
    if regex_count >= 5:
        logger.info(f"EXTRACTION STEP 2: Skipping LLM - {regex_count} entities sufficient")
        final_entities = regex_entities
    else:
        try:
            # Format regex entities for LLM
            regex_summary = _format_entities_for_prompt(regex_entities)
            
            prompt = LLM_VERIFY_PROMPT.format(
                conversation=all_text[:6000],
                regex_entities=regex_summary
            )
            
            response_text = call_llm(
                prompt=prompt,
                system_instruction="You are an entity verification system. VERIFY entities, do NOT invent them.",
                json_mode=True,
                agent_name="extraction"
            )
            
            llm_result = _parse_json_safely(response_text)
            llm_entities = llm_result.get("verified_entities", {})
            obfuscation = llm_result.get("obfuscation_detected", "")
            
            if obfuscation:
                logger.info(f"EXTRACTION: LLM detected obfuscation: {obfuscation}")
            
            # Merge regex + LLM results
            from utils.prefilter import merge_entities
            final_entities = merge_entities(regex_entities, llm_entities)
            
            logger.info(f"EXTRACTION STEP 2: LLM verification complete")
            
        except Exception as e:
            logger.warning(f"LLM verification failed: {e}, using regex-only")
            final_entities = regex_entities
    
    # =========================================================================
    # STEP 3: FILTER LOW-CONFIDENCE ENTITIES
    # =========================================================================
    from utils.prefilter import filter_low_confidence
    
    final_entities = filter_low_confidence(final_entities, threshold=0.6)
    
    final_count = sum(len(v) for v in final_entities.values())
    logger.info(f"EXTRACTION COMPLETE: {final_count} entities after filtering")
    
    # Log results
    from utils.logger import AgentLogger
    AgentLogger.extraction_result(_flatten_entities(final_entities))
    
    return {
        "extracted_entities": final_entities,
        "extraction_complete": False,
        "current_agent": "planner"  # Loop back to planner (Judge merged)
    }


def _merge_entity_dicts(dict1: Dict, dict2: Dict) -> Dict:
    """Merge two entity dictionaries."""
    merged = {}
    all_keys = set(dict1.keys()) | set(dict2.keys())
    
    for key in all_keys:
        list1 = dict1.get(key, [])
        list2 = dict2.get(key, [])
        
        # Get existing values
        values = set()
        merged_list = []
        
        for item in list1 + list2:
            if isinstance(item, dict):
                val = item.get("value", "")
            else:
                val = item
            
            if val and val not in values:
                values.add(val)
                if isinstance(item, dict):
                    merged_list.append(item)
                else:
                    merged_list.append({
                        "value": item,
                        "confidence": 1.0,
                        "source": "explicit"
                    })
        
        merged[key] = merged_list
    
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


def _flatten_entities(entities: Dict) -> Dict:
    """Flatten entity dicts to simple lists for logging."""
    flattened = {}
    for key, items in entities.items():
        values = []
        for item in items:
            if isinstance(item, dict):
                values.append(item.get("value", str(item)))
            else:
                values.append(str(item))
    return flattened

def regex_only_extraction_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fast, deterministic extraction using REGEX ONLY.
    Used during the engagement loop to minimize latency.
    """
    from utils.prefilter import extract_entities_deterministic, merge_entities
    
    conversation_history = state.get("conversation_history", [])
    original_message = state.get("original_message", "")
    
    # Combine all text
    all_text = f"Original message: {original_message}\n\n"
    for turn in conversation_history:
        role = "Honeypot" if turn.get("role") == "honeypot" else "Scammer"
        all_text += f"{role}: {turn.get('message', '')}\n"
        
        revealed = turn.get("revealed_info", {})
        if revealed:
            all_text += f"[Revealed: {json.dumps(revealed)}]\n"
            
    # Run deterministic extraction
    regex_entities = extract_entities_deterministic(all_text)
    regex_count = sum(len(v) for v in regex_entities.values())
    
    logger.info(f"FAST EXTRACTION: Found {regex_count} entities via Regex")
    
    # Merge with existing entities
    current_entities = state.get("extracted_entities", {})
    final_entities = merge_entities(current_entities, regex_entities)
    
    return {
        "extracted_entities": final_entities,
        "extraction_complete": False,
        "current_agent": "planner"
    }
