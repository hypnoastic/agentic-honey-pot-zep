"""
Fact-Checker Agent using Serper API for Internet Verification.
HARDENED: Regex decides IF to fact-check, LLM decides HOW to search.
"""

import re
import httpx
import logging
import json
from typing import Dict, Any, List, Optional

from config import get_settings

logger = logging.getLogger(__name__)

# ============================================================================
# COMPREHENSIVE FACT-CHECK TRIGGERS
# Regex decides WHETHER to fact-check (trust boundary)
# ============================================================================

FACT_CHECK_TRIGGERS = [
    # Government Schemes
    r"(?i)pm\s*(?:kisan|awas|mudra|yojana|scheme|modi|jan\s*dhan|suraksha|jeevan)",
    r"(?i)(?:pradhan\s*mantri|government|sarkar|sarkari)\s*\w+\s*(?:yojana|scheme)",
    r"(?i)(?:subsidy|grant|relief|fund|scholarship|pension)\s*(?:scheme|yojana)",
    
    # Regulatory Bodies
    r"(?i)rbi\s*(?:circular|notice|policy|guideline|regulation|directive|order)",
    r"(?i)(?:sebi|trai|irdai|epfo|pf|cbi|ed|income\s*tax)\s*(?:notice|alert|order|circular)",
    r"(?i)(?:reserve\s*bank|central\s*bank)\s*(?:notice|circular|policy)",
    
    # Income Tax & Refunds
    r"(?i)income\s*tax\s*(?:refund|notice|department|return|assessment)",
    r"(?i)(?:it|itr)\s*(?:refund|notice|pending|verification)",
    r"(?i)tax\s*(?:refund|return|pending|claim)\s*(?:₹|rs\.?|inr)?",
    
    # Bank Impersonation
    r"(?i)(?:sbi|hdfc|icici|axis|pnb|bob|kotak|canara|idbi|yes\s*bank)\s*(?:policy|scheme|offer|notice|alert|security)",
    r"(?i)(?:kyc|pan|aadhaar)\s*(?:link|update|verify|suspend|expired|mandatory)",
    r"(?i)(?:account|card)\s*(?:blocked|suspended|frozen|deactivated)",
    
    # Investment Claims
    r"(?i)\d+[\.\d]*%\s*(?:daily|weekly|monthly|annual)?\s*(?:return|interest|profit|guarantee|assured)",
    r"(?i)(?:double|triple|quadruple)\s*(?:your\s*)?(?:money|investment|income)\s*(?:in|within)?",
    r"(?i)(?:guaranteed|assured|fixed|risk\s*free)\s*(?:return|profit|income)",
    r"(?i)(?:mutual\s*fund|stock|share|crypto|forex)\s*(?:scheme|offer|profit)",
    
    # Prize & Lottery Claims
    r"(?i)(?:₹|rs\.?|inr)\s*[\d,]+\s*(?:lakh|crore|million|billion)",
    r"(?i)(?:won|winner|selected|chosen|lucky)\s*(?:prize|lottery|reward|gift|draw)",
    r"(?i)(?:jio|airtel|vodafone|bsnl|amazon|flipkart|paytm)\s*(?:lucky|winner|prize)",
    r"(?i)whatsapp\s*(?:lucky|winner|prize|lottery)",
    
    # Job Scams
    r"(?i)(?:work\s*from\s*home|part\s*time|online)\s*(?:job|income|earning)",
    r"(?i)(?:amazon|flipkart|google|microsoft)\s*(?:job|hiring|vacancy|offer)",
    r"(?i)(?:registration|joining|training|processing)\s*fee",
    
    # Insurance & Claims
    r"(?i)(?:lic|insurance|policy)\s*(?:maturity|bonus|claim|expired)",
    r"(?i)(?:medical|health)\s*(?:insurance|claim|reimbursement)",
    
    # Electricity & Utility
    r"(?i)(?:electricity|power|water|gas)\s*(?:bill|connection|payment)\s*(?:due|pending|disconnect)",
    r"(?i)(?:mpeb|discom|electricity\s*board)\s*(?:notice|alert)",
]

# ============================================================================
# CLAIM EXTRACTION PATTERNS
# Used to extract specific claims for internet verification
# ============================================================================

CLAIM_PATTERNS = [
    # Government schemes
    (r"(?i)(PM\s+\w+\s+(?:Yojana|Scheme))", "scheme"),
    (r"(?i)((?:Pradhan\s*)?Mantri\s+\w+\s+\w+)", "scheme"),
    (r"(?i)(RBI\s+(?:\w+\s+){1,3}(?:circular|notice|policy))", "regulation"),
    (r"(?i)(SEBI\s+(?:\w+\s+){1,3}(?:order|notice|circular))", "regulation"),
    
    # Bank claims
    (r"(?i)((?:SBI|HDFC|ICICI|Axis|PNB)\s+\w+\s+(?:scheme|offer|policy|notice))", "bank"),
    (r"(?i)(KYC\s+(?:update|link|verify|mandatory)\s+(?:by|before|deadline)?\s*[\d/]+)", "kyc"),
    
    # Investment claims
    (r"(?i)(\d+[\.\d]*%\s*(?:return|interest|profit)[^.!?]{0,50})", "investment"),
    (r"(?i)((?:guaranteed|assured|fixed)\s+\w+\s+(?:return|profit|income))", "investment"),
    
    # Tax claims
    (r"(?i)(Income\s+Tax\s+(?:refund|notice|pending)[^.!?]{0,30})", "tax"),
    (r"(?i)(ITR?\s+\w+\s+(?:refund|pending|claim))", "tax"),
    
    # Prize claims
    (r"(?i)((?:won|selected|winner)\s+(?:₹|Rs\.?|INR)?\s*[\d,]+(?:\s*(?:lakh|crore))?)", "prize"),
    
    # Job claims
    (r"(?i)((?:Amazon|Google|Microsoft)\s+(?:hiring|job\s+offer|vacancy))", "job"),
]


def should_fact_check(message: str) -> bool:
    """
    DETERMINISTIC check: Should we run internet verification?
    This is the TRUST BOUNDARY - regex decides IF, not LLM.
    """
    for pattern in FACT_CHECK_TRIGGERS:
        if re.search(pattern, message):
            logger.info(f"FACT-CHECK TRIGGER: Pattern matched - {pattern[:50]}")
            return True
    return False


async def search_serper(query: str, num_results: int = 3) -> List[Dict[str, Any]]:
    """Search the internet using Serper API."""
    settings = get_settings()
    
    if not settings.serper_api_key or settings.serper_api_key == "your_serper_api_key_here":
        logger.warning("FACT-CHECK: Serper API key not configured")
        return []
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": settings.serper_api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "q": query,
                    "num": num_results,
                    "gl": "in",
                    "hl": "en"
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Serper API error: {response.status_code}")
                return []
            
            data = response.json()
            results = []
            
            for item in data.get("organic", [])[:num_results]:
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "link": item.get("link", ""),
                    "position": item.get("position", 0)
                })
            
            logger.info(f"FACT-CHECK: Serper returned {len(results)} results")
            return results
            
    except httpx.TimeoutException:
        logger.warning("FACT-CHECK: Serper API timeout")
        return []
    except Exception as e:
        logger.error(f"FACT-CHECK: Serper error - {e}")
        return []


def extract_claims_from_message(message: str) -> List[Dict[str, str]]:
    """
    Extract verifiable claims using REGEX (deterministic).
    Returns claims with their type for better search queries.
    """
    claims = []
    
    for pattern, claim_type in CLAIM_PATTERNS:
        matches = re.findall(pattern, message)
        for match in matches:
            if len(match) > 10:
                claims.append({
                    "text": match.strip(),
                    "type": claim_type
                })
    
    # Deduplicate
    seen = set()
    unique = []
    for claim in claims:
        key = claim["text"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(claim)
    
    logger.info(f"FACT-CHECK: Extracted {len(unique)} claims")
    return unique[:3]  # Limit to 3


def build_search_query(claim: Dict[str, str]) -> str:
    """
    Build search query from claim.
    LLM is NOT used here - deterministic query building based on claim type.
    """
    text = claim["text"]
    claim_type = claim["type"]
    
    # Type-specific search suffixes
    suffixes = {
        "scheme": "official government OR scam OR fake",
        "regulation": "official RBI OR scam OR hoax",
        "bank": "official bank OR scam OR phishing",
        "kyc": "scam OR fraud OR fake",
        "investment": "scam OR fraud OR ponzi OR fake",
        "tax": "official income tax OR scam OR fraud",
        "prize": "scam OR fraud OR fake lottery",
        "job": "scam OR fraud OR fake job",
    }
    
    suffix = suffixes.get(claim_type, "scam OR fraud OR fake")
    return f"{text} {suffix}"


TRUSTED_DOMAIN_SUFFIXES = [".gov.in", ".nic.in", "rbi.org.in", "incometax.gov.in"]
SCAM_INDICATOR_KEYWORDS = ["scam", "fraud", "fake", "warning", "beware", "alert", "hoax", "phishing", "malicious"]
LEGIT_INDICATOR_KEYWORDS = ["official", "government", "authorized", "genuine", "original"]

async def verify_claim(claim: Dict[str, str]) -> Dict[str, Any]:
    """
    Verify a single claim using internet search.
    HARDENED: Domain trust → Rank weighting → Confidence score.
    """
    query = build_search_query(claim)
    results = await search_serper(query, num_results=5) # More results for better data
    
    if not results:
        return {
            "claim": claim["text"],
            "type": claim["type"],
            "verified": None,
            "status": "UNKNOWN",
            "confidence": 0.0,
            "reason": "No search results",
            "sources": []
        }
    
    scam_score = 0.0
    legit_score = 0.0
    sources = []
    
    for i, result in enumerate(results):
        # Rank weighting: top results have more weight (1.0, 0.8, 0.6, etc.)
        rank_weight = max(0.2, 1.0 - (i * 0.2))
        
        text = (result["title"] + " " + result["snippet"]).lower()
        link = result["link"].lower()
        
        # 1. Domain Trust Scoring (High Authority)
        domain_legit = False
        for suffix in TRUSTED_DOMAIN_SUFFIXES:
            # Strict domain matching to prevent spoofing (e.g., mysite.gov.in.xyz)
            if link.endswith(suffix) or f"{suffix}/" in link:
                legit_score += 5.0 * rank_weight
                domain_legit = True
                break
        
        # 2. Keyword Scoring (Low Authority - easily gamed)
        for kw in SCAM_INDICATOR_KEYWORDS:
            if kw in text:
                scam_score += 1.0 * rank_weight
                
        for kw in LEGIT_INDICATOR_KEYWORDS:
            if kw in text:
                # If it's a trusted domain, don't double count much, but reinforce
                legit_score += (0.5 if domain_legit else 1.0) * rank_weight
        
        # 3. Domain Red Flags
        if any(link.endswith(ext) for ext in [".xyz", ".top", ".site", ".online", ".zip"]):
             scam_score += 1.0 * rank_weight

        sources.append({
            "title": result["title"][:100],
            "url": result["link"]
        })
    
    # Calculate Confidence (0-1)
    # Based on the margin between scores normalized by total evidence
    total_score = scam_score + legit_score
    if total_score > 0:
        margin = abs(scam_score - legit_score)
        confidence = min(1.0, margin / (total_score * 0.5 + 1.0))
    else:
        confidence = 0.0

    # Determine verdict
    margin = abs(scam_score - legit_score)
    
    if scam_score > legit_score + 1.5:
        status = "LIKELY_SCAM"
        verified = False
        reason = f"Strong scam indicators found ({scam_score:.1f} vs {legit_score:.1f})"
    elif legit_score > scam_score + 1.5:
        status = "POSSIBLY_LEGITIMATE"
        verified = True
        reason = f"Verified via official or authoritative sources ({legit_score:.1f} vs {scam_score:.1f})"
    elif total_score > 1.5:
        # Significant evidence on both sides or mixed signals
        status = "SUSPICIOUS"
        verified = None
        reason = f"Mixed signals detected ({scam_score:.1f} scam vs {legit_score:.1f} legit)"
        confidence = max(confidence, 0.4)
    else:
        status = "INCONCLUSIVE"
        verified = None
        reason = "Limited or contradictory information available"
        confidence = min(confidence, 0.4)
    
    return {
        "claim": claim["text"],
        "type": claim["type"],
        "verified": verified,
        "status": status,
        "confidence": round(confidence, 2),
        "reason": reason,
        "sources": sources[:2]
    }


async def fact_check_message(message: str) -> Dict[str, Any]:
    """
    Main fact-checking function.
    
    HARDENED FLOW:
    1. Regex decides IF to fact-check (trust boundary)
    2. Regex extracts claims (deterministic)
    3. Deterministic query building (no LLM hallucination)
    4. Internet search provides ground truth
    """
    # STEP 1: Regex decides IF to fact-check
    if not should_fact_check(message):
        return {
            "fact_checked": False,
            "reason": "No verifiable claims detected (regex)",
            "results": []
        }
    
    # STEP 2: Extract claims using regex
    claims = extract_claims_from_message(message)
    
    if not claims:
        return {
            "fact_checked": False,
            "reason": "Trigger matched but no specific claims extracted",
            "results": []
        }
    
    # STEP 3: Verify each claim via internet
    import asyncio
    tasks = [verify_claim(claim) for claim in claims]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter exceptions
    valid_results = [r for r in results if isinstance(r, dict)]
    
    # STEP 4: Calculate overall assessment
    scam_count = sum(1 for r in valid_results if r.get("status") == "LIKELY_SCAM")
    suspicious_count = sum(1 for r in valid_results if r.get("status") == "SUSPICIOUS")
    legit_count = sum(1 for r in valid_results if r.get("status") == "POSSIBLY_LEGITIMATE")
    
    # Calculate average confidence
    avg_confidence = sum(r.get("confidence", 0) for r in valid_results) / len(valid_results) if valid_results else 0.0
    
    if scam_count > 0:
        overall_status = "CLAIMS_LIKELY_FRAUDULENT"
        confidence_boost = min(0.2, avg_confidence * 0.3)
    elif suspicious_count > 0:
        overall_status = "CLAIMS_SUSPICIOUS"
        confidence_boost = min(0.1, avg_confidence * 0.15)
    elif legit_count == len(valid_results) and valid_results:
        overall_status = "CLAIMS_APPEAR_LEGITIMATE"
        confidence_boost = -0.1
    else:
        overall_status = "CLAIMS_INCONCLUSIVE"
        confidence_boost = 0.0
    
    logger.info(f"FACT-CHECK COMPLETE: {overall_status} (Conf: {avg_confidence:.2f})")
    
    return {
        "fact_checked": True,
        "overall_status": overall_status,
        "confidence_score": round(avg_confidence, 2),
        "confidence_boost": confidence_boost,
        "claims_checked": len(valid_results),
        "results": valid_results
    }
