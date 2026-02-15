import asyncio
import httpx
import json
import logging
import uuid
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("PAYLOAD_TEST")

BASE_URL = "http://localhost:8000"
HEADERS = {"x-api-key": "langfastgeminihoneypot1234", "Content-Type": "application/json"}

async def test_payload():
    session_id = str(uuid.uuid4())
    
    # EXACT Payload from User Request
    payload = {
      "sessionId": session_id,
      "message": {
        "sender": "scammer",
        "text": "URGENT: Your account has been compromised...",
        "timestamp": 1234567890 # User had string, schema expects int/string. Let's test with int first as per schema, or string if we want to test robustness. User sample had string timestamp.
      },
      "conversationHistory": [
        {
          "sender": "scammer",
          "text": "Previous message...",
          "timestamp": 1234567000
        },
        {
          "sender": "user",
          "text": "Your previous response...",
          "timestamp": 1234567100
        }
      ],
      "metadata": {
        "channel": "SMS",
        "language": "English",
        "locale": "IN"
      }
    }
    
    # Note: User's sample had "timestamp": "2025-02-11T10:30:00Z" (ISO string). 
    # Our schema `HackathonMessage` defines timestamp as `Optional[int]`.
    # `AnalyzeRequest` defines `message` as Union[str, HackathonMessage, Dict].
    # If we pass a string timestamp, strict Pydantic validation for `HackathonMessage` might fail if it expects int. 
    # BUT `Dict[str, Any]` is also allowed. Pydantic tries to match in order. 
    # Let's test with the STRING timestamp to see if it handles it (via Dict fallback).
    
    payload_with_iso_timestamp = payload.copy()
    payload_with_iso_timestamp["message"] = {
        "sender": "scammer",
        "text": "URGENT: ISO TIMESTAMP TEST",
        "timestamp": "2025-02-11T10:30:00Z" 
    }
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        logger.info(f"--- Sending Payload (Session: {session_id}) ---")
        logger.info(f"Payload: {json.dumps(payload_with_iso_timestamp, indent=2)}")
        
        response = await client.post("/analyze", json=payload_with_iso_timestamp, headers=HEADERS)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Success (200): {data}")
            # We can't easily see internal state here, but we can check server logs for 'Conversation history: 2 prior messages'
        elif response.status_code == 422:
             logger.error(f"❌ 422 Validation Error: {response.text}")
        else:
            logger.error(f"❌ Failed: {response.status_code} - {response.text}")

if __name__ == "__main__":
    asyncio.run(test_payload())
