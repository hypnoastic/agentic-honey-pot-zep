import asyncio
import uuid
import json
import logging
import sys
import os
from datetime import datetime
from typing import Dict, Any, List

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Mock Scenario
TEST_SCENARIO = {
    'scenarioId': 'bank_fraud',
    'initialMessage': 'URGENT: Your SBI account has been compromised. Share OTP immediately.',
    'metadata': {'channel': 'SMS', 'language': 'English', 'locale': 'IN'},
    'maxTurns': 10,
    'fakeData': {
        'bankAccount': '1234567890123456',
        'upiId': 'scammer.fraud@fakebank',
        'phoneNumber': '+91-9876543210',
        'email': 'scammer@fake.com'  # Testing new email extraction
    }
}

async def run_verification():
    """Run full evaluation verification."""
    session_id = str(uuid.uuid4())
    logger.info(f"🚀 Starting Evaluation Verification | Session: {session_id}")
    
    headers = {"x-api-key": "langfastgeminihoneypot1234", "Content-Type": "application/json"}
    conversation_history = []
    
    async with AsyncClient(base_url="http://localhost:8000", timeout=120.0) as client:
        
        # 1. Start Conversation
        current_message = TEST_SCENARIO['initialMessage']
        
        for turn in range(1, TEST_SCENARIO['maxTurns'] + 1):
            logger.info(f"\n--- Turn {turn} ---")
            logger.info(f"Scammer: {current_message}")
            
            # Prepare Payload
            payload = {
                "sessionId": session_id,
                "message": {
                    "sender": "scammer",
                    "text": current_message,
                    "timestamp": int(datetime.utcnow().timestamp())
                },
                "conversationHistory": conversation_history,
                "metadata": TEST_SCENARIO['metadata']
            }
            # logger.info(f"📤 Payload: {json.dumps(payload)}")
            
            # Call API
            response = await client.post("/analyze", json=payload, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"❌ API Failed Status: {response.status_code}")
                logger.error(f"Response: {response.text}")
                break
                
            data = response.json()
            reply = data.get("reply")
            strategy = data.get("strategy_hint", "N/A")
            logger.info(f"🧠 Strategy: {strategy}")
            logger.info(f"✅ Honeypot: {reply}")
            print(f"Scammer: {current_message}\nStrategy: {strategy}\nHoneypot: {reply}\n{'-'*20}")
            
            # Update History
            conversation_history.append({"sender": "scammer", "text": str(current_message), "timestamp": int(datetime.utcnow().timestamp())})
            conversation_history.append({"sender": "user", "text": str(reply or "Thinking..."), "timestamp": int(datetime.utcnow().timestamp())})
            
            # Check for conclusion - SMARTER ENGAGEMENT TEST (T8/T9 Leakage)
            if turn >= 8: 
                if turn == 8: current_message = f"Fine. My bank account is {TEST_SCENARIO['fakeData']['bankAccount']}"
                elif turn == 9: current_message = f"Email me at {TEST_SCENARIO['fakeData']['email']}"
                else: current_message = "Did you get it all?"
            else:
                current_message = "I need you to verify quickly. Why are you asking so many questions?"
                
            # If engagement complete
            if data.get("engagement_count", 0) >= 10:
                logger.info("🛑 Max turns reached.")
                break
                
        logger.info("\n✨ Verification Complete. Check logs above for '[GUVI] 📞 Sending Report'")

if __name__ == "__main__":
    # Ensure settings are loaded
    os.environ["POSTGRES_ENABLED"] = "false" # Use local mock for speed if needed, or true
    asyncio.run(run_verification())
