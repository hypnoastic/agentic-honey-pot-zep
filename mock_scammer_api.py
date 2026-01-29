"""
Mock Scammer API for testing the honeypot system.
Simulates realistic scammer behavior with progressive information revelation.
"""

import uuid
import random
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Mock Scammer API",
    description="Simulates scammer behavior for honeypot testing",
    version="1.0.0"
)

# In-memory conversation state
conversations: Dict[str, dict] = {}


class EngagementRequest(BaseModel):
    """Request from honeypot to mock scammer."""
    victim_message: str = Field(..., description="Message from the honeypot persona")
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    turn_number: int = Field(default=1)


class ScammerResponse(BaseModel):
    """Response from mock scammer."""
    message: str
    revealed_info: Optional[dict] = None
    conversation_ended: bool = False


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

# Fake data for revelation
FAKE_UPI_IDS = ["scammer2024@paytm", "lottery.winner@gpay", "bank.verify@ybl", "prize.claim@upi"]
FAKE_BANK_ACCOUNTS = ["1234567890123456", "9876543210987654", "5678901234567890"]
FAKE_PHISHING_URLS = [
    "http://sbi-kyc-verify.fake.com/update",
    "http://prize-claim-portal.scam.net/form",
    "http://bank-security-check.fraud.org/verify"
]


def get_scammer_response(conversation_id: str, turn: int, victim_message: str) -> ScammerResponse:
    """Generate scammer response based on conversation state."""
    
    # Initialize or get conversation state
    if conversation_id not in conversations:
        conversations[conversation_id] = {
            "turn": 0,
            "revealed_upi": False,
            "revealed_bank": False,
            "revealed_url": False,
            "upi_id": random.choice(FAKE_UPI_IDS),
            "bank_account": random.choice(FAKE_BANK_ACCOUNTS),
            "url": random.choice(FAKE_PHISHING_URLS)
        }
    
    state = conversations[conversation_id]
    state["turn"] = turn
    revealed_info = {}
    
    # Determine response based on turn and what victim says
    victim_lower = victim_message.lower()
    
    # Check for interest signals
    shows_interest = any(word in victim_lower for word in [
        "yes", "interested", "how", "tell me", "what", "proceed", 
        "okay", "sure", "details", "send", "transfer", "pay"
    ])
    
    shows_hesitation = any(word in victim_lower for word in [
        "suspicious", "fraud", "police", "scam", "fake", "don't trust"
    ])
    
    if shows_hesitation:
        # Try to build trust
        message = random.choice(SCAMMER_RESPONSES["requesting_trust"])
        
    elif turn == 1:
        # Initial greeting
        message = random.choice(SCAMMER_RESPONSES["initial"])
        
    elif turn == 2 and shows_interest:
        # Reveal UPI
        state["revealed_upi"] = True
        message = random.choice(SCAMMER_RESPONSES["revealing_upi"]).format(upi_id=state["upi_id"])
        revealed_info["upi_id"] = state["upi_id"]
        
    elif turn == 3 and shows_interest:
        # Reveal bank account
        state["revealed_bank"] = True
        message = random.choice(SCAMMER_RESPONSES["revealing_bank"]).format(bank_account=state["bank_account"])
        revealed_info["bank_account"] = state["bank_account"]
        
    elif turn == 4 and shows_interest:
        # Reveal phishing URL
        state["revealed_url"] = True
        message = random.choice(SCAMMER_RESPONSES["revealing_url"]).format(url=state["url"])
        revealed_info["url"] = state["url"]
        
    elif turn >= 5:
        # Final message, end conversation
        message = random.choice(SCAMMER_RESPONSES["final"])
        return ScammerResponse(
            message=message,
            revealed_info=revealed_info if revealed_info else None,
            conversation_ended=True
        )
        
    else:
        # Apply pressure
        message = random.choice(SCAMMER_RESPONSES["pressure"])
    
    return ScammerResponse(
        message=message,
        revealed_info=revealed_info if revealed_info else None,
        conversation_ended=False
    )


@app.post("/engage", response_model=ScammerResponse)
async def engage_scammer(request: EngagementRequest):
    """
    Simulate scammer engagement.
    Returns scammer's response and any revealed information.
    """
    return get_scammer_response(
        request.conversation_id,
        request.turn_number,
        request.victim_message
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "mock-scammer-api"}


@app.delete("/conversations/{conversation_id}")
async def clear_conversation(conversation_id: str):
    """Clear a specific conversation state."""
    if conversation_id in conversations:
        del conversations[conversation_id]
        return {"status": "cleared"}
    raise HTTPException(status_code=404, detail="Conversation not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
