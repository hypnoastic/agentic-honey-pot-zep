"""
Deterministic Scam Pre-Filter Layer
Runs BEFORE any LLM call to detect obvious scams.
Reduces latency, cost, and hallucination surface.
"""

import re
import logging
from typing import Dict, Any, Tuple, List, Set

logger = logging.getLogger(__name__)

# ============================================================================
# SCAM PATTERN DEFINITIONS
# Each pattern includes a type, confidence weight, and regex
# ============================================================================

SCAM_PATTERNS: Dict[str, List[Tuple[str, float]]] = {
    "UPI_FRAUD": [
        (r"(?i)(?:send|pay|transfer)\s*(?:₹|rs\.?|inr)?\s*[\d,]+\s*(?:to|@)", 0.7),
        (r"(?i)\w+@(?:upi|paytm|gpay|phonepe|ybl|oksbi|okaxis|okicici|okhdfcbank|axl)\b", 0.8),
        (r"(?i)(?:processing|verification|refund|registration)\s*fee", 0.75),
        (r"(?i)(?:upi|gpay|paytm)\s*(?:id|number|pin)", 0.6),
        (r"(?i)collect\s*request", 0.7),
    ],
    "BANK_IMPERSONATION": [
        (r"(?i)(?:kyc|pan|aadhaar)\s*(?:update|verify|expired|suspended|link)", 0.85),
        (r"(?i)(?:sbi|hdfc|icici|axis|pnb|bob|kotak|canara|union)\s*(?:alert|notice|suspended|blocked|security)", 0.8),
        (r"(?i)account\s*(?:suspended|blocked|frozen|deactivat)", 0.75),
        (r"(?i)dear\s*(?:customer|user|valued)\s*(?:your\s*)?(?:account|card)", 0.7),
        (r"(?i)(?:credit|debit)\s*card\s*(?:block|suspend|expir)", 0.75),
        (r"(?i)(?:otp|cvv|pin)\s*(?:share|send|provide|verify)", 0.9),
    ],
    "LOTTERY_FRAUD": [
        (r"(?i)(?:won|winner|selected|chosen|lucky)\s*(?:prize|lottery|draw|reward|gift)", 0.85),
        (r"(?i)(?:₹|rs\.?|inr)\s*[\d,]+\s*(?:lakh|crore|million|billion)", 0.7),
        (r"(?i)claim\s*(?:your\s*)?(?:prize|reward|money|gift|winning)", 0.8),
        (r"(?i)(?:jio|airtel|vodafone|bsnl)\s*(?:lucky|winner|prize)", 0.85),
        (r"(?i)whatsapp\s*(?:lucky|winner|prize)", 0.9),
        (r"(?i)(?:amazon|flipkart)\s*(?:lucky|winner|prize|gift)", 0.85),
    ],
    "GOVERNMENT_SCHEME": [
        (r"(?i)pm\s*(?:kisan|awas|mudra|yojana|scheme|modi|jan\s*dhan)", 0.7),
        (r"(?i)(?:pradhan\s*mantri|government|sarkar|sarkari)\s*\w+\s*(?:yojana|scheme)", 0.7),
        (r"(?i)(?:subsidy|grant|relief|fund|scholarship)\s*(?:scheme|yojana)", 0.65),
        (r"(?i)rbi\s*(?:circular|notice|policy|guideline|regulation)", 0.7),
        (r"(?i)(?:sebi|trai|irdai|epfo|pf)\s*(?:notice|alert|order)", 0.7),
        (r"(?i)income\s*tax\s*(?:refund|notice|department|return)", 0.7),
    ],
    "PHISHING": [
        (r"https?://(?:bit\.ly|tinyurl\.com|goo\.gl|is\.gd|t\.co)/\w+", 0.75),
        (r"(?i)(?:click|verify|confirm|update)\s*(?:here|link|button|now|immediately)", 0.6),
        (r"(?i)(?:expire|suspend|block)\s*(?:in|within)\s*\d+\s*(?:hour|day|minute)", 0.75),
        (r"(?i)update.*(?:details|information|profile).*(?:link|form|click)", 0.7),
        (r"(?i)verify\s*(?:your\s*)?(?:identity|account|email|phone)", 0.6),
    ],
    "INVESTMENT_SCAM": [
        (r"(?i)\d+[\.\d]*%\s*(?:daily|weekly|monthly)?\s*(?:return|interest|profit|guarantee)", 0.85),
        (r"(?i)(?:double|triple|quadruple)\s*(?:your\s*)?(?:money|investment|income)", 0.9),
        (r"(?i)(?:guaranteed|assured|fixed)\s*(?:return|profit|income)", 0.85),
        (r"(?i)(?:crypto|bitcoin|forex|trading)\s*(?:profit|earn|invest)", 0.7),
        (r"(?i)risk\s*free\s*(?:investment|income|return)", 0.9),
    ],
    "JOB_SCAM": [
        (r"(?i)(?:work\s*from\s*home|part\s*time|online)\s*(?:job|income|earning)", 0.6),
        (r"(?i)(?:registration|joining|training)\s*fee", 0.8),
        (r"(?i)earn\s*(?:₹|rs\.?|inr)?\s*[\d,]+\s*(?:daily|weekly|monthly)", 0.75),
        (r"(?i)(?:hiring|vacancy|job\s*offer).*(?:whatsapp|telegram)", 0.7),
        (r"(?i)no\s*(?:experience|qualification|skill)\s*(?:required|needed)", 0.6),
    ],
    "TECH_SUPPORT_SCAM": [
        (r"(?i)(?:virus|malware|hacked|compromised)\s*(?:detected|found|alert)", 0.8),
        (r"(?i)(?:microsoft|apple|google)\s*(?:support|security|alert)", 0.75),
        (r"(?i)(?:remote|anydesk|teamviewer)\s*(?:access|support)", 0.7),
        (r"(?i)(?:computer|device|phone)\s*(?:infected|hacked|at\s*risk)", 0.75),
    ],
}

# Entity extraction patterns
ENTITY_PATTERNS: Dict[str, List[str]] = {
    "upi_ids": [
        r"\b[\w\.\-]+@(?:upi|paytm|gpay|phonepe|ybl|oksbi|okaxis|okicici|okhdfcbank|axl|apl|ibl|sbi|icici|hdfc|yesbank|axisbank|fakebank)\b",
    ],
    "bank_accounts": [
        # Match 11-18 digit numbers (avoids 10-digit Indian phone numbers)
        r"\b\d{11,18}\b",
        # Also match explicitly labelled account numbers that may be shorter
        r"(?i)(?:account|a\/c|acct)[\s#:]*(\d{9,18})\b",
    ],
    "ifsc_codes": [
        r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
    ],
    "phone_numbers": [
        r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b",
    ],
    "phishing_urls": [
        r"https?://[^\s<>\"']+",
        r"\b(?:bit\.ly|tinyurl\.com|goo\.gl|is\.gd|t\.co)/[\w]+",
    ],
    "email_addresses": [
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    ],
    "case_ids": [
        r"\b(?:case|complaint|ticket|ref|reference)\s*(?:no\.?|number|id|#)\s*[A-Z0-9\-]{4,20}\b",
        r"\bCASE[-/]?\d{4,15}\b",
        r"\bCRN[-/]?\d{6,15}\b",
    ],
    "policy_numbers": [
        r"\b(?:policy|pol\.?)\s*(?:no\.?|number|#)\s*[A-Z0-9\-]{5,20}\b",
        r"\b(?:LIC|SBI|HDFC|ICICI|BAJAJ|MAX|TATA)[-/]?\d{8,14}\b",
        r"\b\d{6,9}[-/]\d{2,3}[-/]\d{2,5}\b",  # 123456789/01/001 style
    ],
    "order_numbers": [
        r"\b(?:order|ord\.?)\s*(?:no\.?|number|id|#)\s*[A-Z0-9\-]{5,20}\b",
        r"\b(?:OD|ORD|INV|TXN|REF)\d{8,15}\b",
        r"\b\d{3}[-\s]\d{7}[-\s]\d{7}\b",  # Amazon-style order numbers
    ],
}


def prefilter_scam_detection(message: str) -> Tuple[bool, str, float, List[str]]:
    """
    Deterministic pre-filter for scam detection.
    Runs BEFORE LLM to catch obvious scams.
    
    Args:
        message: Input message to analyze
        
    Returns:
        Tuple of (is_obvious_scam, scam_type, confidence, indicators)
    """
    if not message or len(message) < 10:
        return (False, None, 0.0, [])
    
    message_lower = message.lower()
    
    matched_types: Dict[str, float] = {}
    all_indicators: List[str] = []
    
    for scam_type, patterns in SCAM_PATTERNS.items():
        type_score = 0.0
        type_matches = 0
        
        for pattern, weight in patterns:
            if re.search(pattern, message, re.IGNORECASE):
                type_score += weight
                type_matches += 1
                # Extract matched text as indicator
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    indicator_text = match.group(0)[:50]  # Cap length
                    all_indicators.append(f"{scam_type}: {indicator_text}")
        
        if type_matches > 0:
            # Normalize score and boost for multiple matches
            normalized_score = min(1.0, (type_score / type_matches) + (0.05 * (type_matches - 1)))
            matched_types[scam_type] = normalized_score
    
    if not matched_types:
        return (False, None, 0.0, [])
    
    # Get highest scoring type
    best_type = max(matched_types, key=matched_types.get)
    best_score = matched_types[best_type]
    
    # Cross-type boost: if multiple types match, it's more likely a scam
    if len(matched_types) > 1:
        best_score = min(1.0, best_score + 0.1)
    
    # Threshold for "obvious" scam (skip LLM)
    is_obvious = best_score >= 0.85
    
    logger.debug(f"PREFILTER: Type={best_type}, Score={best_score:.2f}, Obvious={is_obvious}, Indicators={len(all_indicators)}")
    
    return (is_obvious, best_type, best_score, all_indicators[:5])


def extract_entities_deterministic(text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Deterministic regex-based entity extraction.
    Returns entities with confidence and source attribution.
    
    Args:
        text: Text to extract entities from
        
    Returns:
        Dict with entity types as keys and lists of entity dicts
    """
    entities: Dict[str, List[Dict[str, Any]]] = {}
    
    for entity_type, patterns in ENTITY_PATTERNS.items():
        matches: Set[str] = set()
        
        for pattern in patterns:
            found = re.findall(pattern, text, re.IGNORECASE)
            matches.update(found)
        
        # Create entity objects with metadata
        entity_list = []
        for match in matches:
            # Clean and normalize
            clean_match = match.strip()
            if entity_type == "bank_accounts":
                clean_match = re.sub(r'\s+', '', clean_match)  # Remove spaces
            
            # Skip obvious false positives
            if entity_type == "bank_accounts" and len(clean_match) < 9:
                continue
            if entity_type == "phone_numbers" and len(re.sub(r'\D', '', clean_match)) < 10:
                continue
                
            entity_list.append({
                "value": clean_match,
                "confidence": 1.0,  # Regex matches are explicit
                "source": "explicit"
            })
        
        entities[entity_type] = entity_list
    
    total = sum(len(v) for v in entities.values())
    logger.debug(f"PREFILTER EXTRACTION: Found {total} entities via regex")
    
    return entities


def merge_entities(regex_entities: Dict, llm_entities: Dict) -> Dict[str, List[Dict[str, Any]]]:
    """
    Merge regex-extracted and LLM-verified entities using the specialized 
    logic in agents.entity_utils.
    """
    from agents.entity_utils import merge_entities as core_merge
    return core_merge(regex_entities, llm_entities)


def filter_low_confidence(entities: Dict[str, List[Dict]], threshold: float = 0.6) -> Dict[str, List[Dict]]:
    """
    Filter out entities with confidence below threshold.
    
    Args:
        entities: Entity dict with confidence scores
        threshold: Minimum confidence to keep (default 0.6)
        
    Returns:
        Filtered entity dict
    """
    filtered = {}
    discarded_count = 0
    
    for entity_type, entity_list in entities.items():
        filtered[entity_type] = []
        for entity in entity_list:
            if isinstance(entity, dict):
                conf = entity.get("confidence", 1.0)
                if conf >= threshold:
                    filtered[entity_type].append(entity)
                else:
                    discarded_count += 1
                    logger.debug(f"Discarded low-confidence entity: {entity}")
            else:
                # Legacy format: keep as-is
                filtered[entity_type].append(entity)
    
    if discarded_count > 0:
        logger.debug(f"PREFILTER: Discarded {discarded_count} low-confidence entities")
    
    return filtered
