"""
Confidence Scoring Agent
Calculates confidence score based on multiple factors.
Fixed weighted average calculation.
"""

from typing import Dict, Any


def confidence_scoring_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate overall confidence score for the scam detection and extraction.
    
    Factors considered:
    - Scam indicator strength
    - Number of entities extracted
    - Entity validation
    - Conversation coherence
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with confidence scoring
    """
    factors = {}
    
    # Factor 1: Initial detection confidence (already set)
    initial_confidence = state.get("confidence_score", 0.0)
    factors["initial_detection"] = initial_confidence
    
    # Factor 2: Scam indicators count (max 0.3)
    indicators = state.get("scam_indicators", [])
    indicator_score = min(len(indicators) * 0.1, 0.3)
    factors["indicator_strength"] = indicator_score
    
    # Factor 3: Entity extraction success (max 0.4)
    entities = state.get("extracted_entities", {})
    entity_count = (
        len(entities.get("bank_accounts", [])) +
        len(entities.get("upi_ids", [])) +
        len(entities.get("phishing_urls", []))
    )
    entity_score = min(entity_count * 0.15, 0.4)
    factors["entity_extraction"] = entity_score
    
    # Factor 4: Conversation engagement (max 0.2)
    conversation = state.get("conversation_history", [])
    engagement_score = min(len(conversation) * 0.05, 0.2)
    factors["engagement_depth"] = engagement_score
    
    # Factor 5: Scam type validation (0.1 if type identified)
    scam_type = state.get("scam_type")
    type_score = 0.1 if scam_type else 0.0
    factors["type_validation"] = type_score
    
    # Calculate weighted final score
    if state.get("scam_detected"):
        # For detected scams, use weighted average
        weights = {
            "initial_detection": 0.35,
            "indicator_strength": 0.15,
            "entity_extraction": 0.25,
            "engagement_depth": 0.15,
            "type_validation": 0.10
        }
        
        # Fixed: Correct weighted average calculation
        final_score = sum(
            factors[key] * weights[key]
            for key in weights
        )
        
        # Normalize: initial_detection is already 0-1, others are capped
        # Boost if we have high initial confidence
        if initial_confidence > 0.8:
            final_score = min(final_score + 0.2, 0.99)
        
        # Boost if we extracted entities
        if entity_count > 0:
            final_score = min(final_score + 0.1, 0.99)
        
        # Ensure score is between 0 and 1
        final_score = min(max(final_score, 0.0), 0.99)
            
    else:
        # Non-scam: keep low confidence
        final_score = max(0.0, 1.0 - initial_confidence) * 0.3
    
    return {
        "confidence_score": round(final_score, 2),
        "confidence_factors": factors,
        "current_agent": "response_formatter"
    }
