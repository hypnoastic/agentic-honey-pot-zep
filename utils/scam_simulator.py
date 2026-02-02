"""
Scam Simulator
Internal utility to simulate realistic scammer behavior for system validation and testing.
Replaces external mock API with a production-grade internal class.
"""

import random
import uuid
from typing import Dict, Optional, List

# Scammer persona templates
SCAMMER_RESPONSES = {
    "initial": [
        "Hello dear! Yes, you have won a special prize of Rs 1,00,000! Please share your details to claim.",
        "Congratulations! I am calling from State Bank. Your KYC needs updating. Please cooperate.",
        "Sir/Madam, this is urgent! Your bank account will be blocked unless you verify now.",
    ],
    "requesting_trust": [
        "Sir, don't worry, this is 100% genuine. I am senior officer from head office.",
        "Madam ji, lakhs of people have already received their prize. You will also get!",
        "Please trust me, I am here to help you only. No fraud, completely safe.",
    ],
    "revealing_upi": [
        "Just send small processing fee of Rs 500 to my UPI: {upi_id} and prize will be transferred.",
        "For verification, transfer Rs 1 to this UPI ID: {upi_id}. This is mandatory process.",
        "Send token amount to UPI: {upi_id} and your full prize money will come in 24 hours.",
    ],
    "revealing_bank": [
        "If UPI not working, transfer to account number {bank_account}, IFSC: SBIN0001234",
        "You can also do NEFT to account: {bank_account}, name: Prize Claims Dept",
        "Bank transfer also accepted: Account {bank_account}, any bank will work.",
    ],
    "revealing_url": [
        "For faster processing, fill form at {url} with your bank details.",
        "Visit {url} to complete KYC and unlock your prize instantly!",
        "Click here to verify: {url} - official bank verification portal.",
    ],
    "pressure": [
        "Sir, offer expires in 30 minutes! Act fast or prize goes to someone else!",
        "Last warning! Your account will be frozen if you don't complete verification NOW!",
        "Madam, why delay? This is once in lifetime opportunity, don't miss!",
    ],
    "final": [
        "Thank you for your cooperation. Processing will complete soon.",
        "Your request is noted. Prize/refund will reflect in your account shortly.",
        "Transaction initiated. Please wait 24-48 hours for completion.",
    ]
}

FAKE_UPI_IDS = ["scammer2024@paytm", "lottery.winner@gpay", "bank.verify@ybl", "prize.claim@upi"]
FAKE_BANK_ACCOUNTS = ["1234567890123456", "9876543210987654", "5678901234567890"]
FAKE_PHISHING_URLS = [
    "http://sbi-kyc-verify.fake.com/update",
    "http://prize-claim-portal.scam.net/form",
    "http://bank-security-check.fraud.org/verify"
]

class ScamSimulator:
    """Simulates a scammer with stateful progressive information revelation."""
    
    def __init__(self):
        self._conversations: Dict[str, Dict] = {}

    def get_response(self, conversation_id: str, turn: int, victim_message: str) -> Dict:
        """Calculate the simulated scammer response."""
        
        # Initialize state if new
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = {
                "upi_id": random.choice(FAKE_UPI_IDS),
                "bank_account": random.choice(FAKE_BANK_ACCOUNTS),
                "url": random.choice(FAKE_PHISHING_URLS)
            }
        
        state = self._conversations[conversation_id]
        revealed_info = {}
        message = ""
        ended = False
        
        victim_lower = victim_message.lower()
        
        # Detection logic
        shows_interest = any(w in victim_lower for w in ["yes", "interested", "how", "tell", "proceed", "okay", "sure", "details", "send", "pay"])
        shows_hesitation = any(w in victim_lower for w in ["suspicious", "fraud", "police", "scam", "fake", "trust"])
        
        if shows_hesitation:
            message = random.choice(SCAMMER_RESPONSES["requesting_trust"])
        elif turn == 1:
            message = random.choice(SCAMMER_RESPONSES["initial"])
        elif turn == 2 and shows_interest:
            message = random.choice(SCAMMER_RESPONSES["revealing_upi"]).format(upi_id=state["upi_id"])
            revealed_info["upi_id"] = state["upi_id"]
        elif turn == 3 and shows_interest:
            message = random.choice(SCAMMER_RESPONSES["revealing_bank"]).format(bank_account=state["bank_account"])
            revealed_info["bank_account"] = state["bank_account"]
        elif turn == 4 and shows_interest:
            message = random.choice(SCAMMER_RESPONSES["revealing_url"]).format(url=state["url"])
            revealed_info["url"] = state["url"]
        elif turn >= 5:
            message = random.choice(SCAMMER_RESPONSES["final"])
            ended = True
        else:
            message = random.choice(SCAMMER_RESPONSES["pressure"])
            
        return {
            "message": message,
            "revealed_info": revealed_info or None,
            "conversation_ended": ended
        }

# Global singleton
simulator = ScamSimulator()
