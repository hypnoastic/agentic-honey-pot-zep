"""
Fallback Response Templates for Persona Engagement.
Used when LLM generation fails or for rapid prototyping.
"""

import random
from typing import Dict, List

# Fallback templates organized by scam type and strategy
FALLBACK_TEMPLATES: Dict[str, List[str]] = {
    "stall": [
        "Sir, please wait. I am checking with my son who knows computers.",
        "One moment please, my reading glasses are broken. Can you type slower?",
        "Hold on, I have another call coming. Will message you back.",
        "My phone battery is low, let me charge it first.",
        "Sorry, I don't understand. Can you explain in simple words?",
    ],
    "confusion": [
        "What is UPI? I only use bank passbook for transactions.",
        "I don't know how to click links on phone. Is there SBI branch I can visit?",
        "My grandson set up this phone. I don't know how to use it properly.",
        "Can you call me instead? I am not good at typing messages.",
        "What is OTP? Is it like PIN number?",
    ],
    "compliance": [
        "Yes sir, I will do whatever you say. Please guide me step by step.",
        "Okay, I am ready. What should I do first?",
        "I trust you completely. You sound like a genuine bank officer.",
        "Thank you for helping me. I was very worried about my account.",
        "I have my passbook ready. What details do you need?",
    ],
    "interest": [
        "Really? I can win this prize? That is wonderful news!",
        "How much money will I receive? My son's wedding is coming up.",
        "Is this genuine offer? My friend told me about internet frauds.",
        "What documents do I need to submit for this scheme?",
        "I am very interested. Please tell me the full procedure.",
    ],
    "probe": [
        "Before I proceed, can you give me your employee ID number?",
        "Which branch are you calling from? I want to visit personally.",
        "Can you give me a landline number to call back and verify?",
        "What is the official website where I can check this offer?",
        "I want to confirm - you are from which government department?",
    ],
}

SCAM_TYPE_STRATEGIES: Dict[str, List[str]] = {
    "UPI_FRAUD": ["stall", "confusion", "probe"],
    "BANK_IMPERSONATION": ["confusion", "compliance", "probe"],
    "LOTTERY_FRAUD": ["interest", "stall", "probe"],
    "INVESTMENT_SCAM": ["interest", "stall", "probe"],
    "TECH_SUPPORT_SCAM": ["confusion", "stall"],
    "PHISHING": ["confusion", "stall"],
    "JOB_SCAM": ["interest", "compliance"],
    "ROMANCE_SCAM": ["compliance", "stall"],
}


def get_fallback_response(scam_type: str, strategy: str = None) -> str:
    """
    Get a fallback response template.
    
    Args:
        scam_type: Type of scam detected
        strategy: Optional strategy hint from planner
        
    Returns:
        A fallback response string
    """
    # Determine strategy
    if not strategy:
        strategies = SCAM_TYPE_STRATEGIES.get(scam_type, ["stall", "confusion"])
        strategy = random.choice(strategies)
    
    # Normalize strategy to template key
    strategy_key = strategy.lower()
    for key in FALLBACK_TEMPLATES:
        if key in strategy_key:
            strategy_key = key
            break
    else:
        strategy_key = "stall"  # Default
    
    # Get random template from strategy
    templates = FALLBACK_TEMPLATES.get(strategy_key, FALLBACK_TEMPLATES["stall"])
    return random.choice(templates)


def get_emergency_fallback() -> str:
    """Get an emergency fallback for any situation."""
    emergency = [
        "Please wait, I am confused. Can you explain again?",
        "Sir, hold on. My network is very slow here.",
        "One moment please, someone is at my door.",
        "Sorry, I didn't understand. Please repeat.",
    ]
    return random.choice(emergency)
