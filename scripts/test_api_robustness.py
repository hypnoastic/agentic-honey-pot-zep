import asyncio
import httpx
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("API_TEST")

BASE_URL = "http://localhost:8000"
HEADERS = {"x-api-key": "langfastgeminihoneypot1234", "Content-Type": "application/json"}

async def test_request(name, payload, expected_status=200):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        try:
            logger.info(f"--- Testing: {name} ---")
            response = await client.post("/analyze", json=payload, headers=HEADERS)
            
            if response.status_code == expected_status:
                data = response.json()
                reply = data.get('reply')
                reply_preview = reply[:50] if reply else "No Reply"
                logger.info(f"✅ Success ({response.status_code}): {data.get('status')} | Reply: {reply_preview}...")
            else:
                logger.error(f"❌ Failed: Got {response.status_code} (Expected {expected_status})")
                logger.error(f"Response: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Exception: {e}")

async def run_tests():
    # 1. Normal Request
    await test_request("Normal Request", {
        "message": "Hello, I am a Prince.",
        "conversation_id": "test-123"
    })

    # 2. Empty Message (Should trigger fallback)
    await test_request("Empty Message", {
        "message": "",
        "conversation_id": "test-empty"
    })

    # 3. Message as Dict (Schema allows Union[str, Dict])
    await test_request("Message as Dict", {
        "message": {"text": "I am a dict message", "extra": "ignore me"},
        "conversation_id": "test-dict"
    })

    # 4. Missing Conversation ID (Should auto-generate)
    await test_request("Missing ID", {
        "message": "No ID provided"
    })
    
    # 5. Invalid UUID (Should handle gracefully)
    await test_request("Invalid UUID", {
        "message": "Bad UUID",
        "conversation_id": "not-a-uuid"
    })
    
    # 6. Malformed History (Should ignore or handle)
    await test_request("Malformed History", {
        "message": "History test",
        "conversationHistory": [{"sender": "user", "text": "hi", "timestamp": "not-an-int"}] # Timestamp string might fail validation if schema ignores, let's see
    }, expected_status=422) # Pydantic strict types usually 422

if __name__ == "__main__":
    asyncio.run(run_tests())
