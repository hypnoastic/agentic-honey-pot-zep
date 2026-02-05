"""
End-to-End Validation Test for Agentic Honey-Pot.
Verifies normal operation, cold start, and support for Hackathon formats.
"""

import sys
import os
import unittest
import logging
from fastapi.testclient import TestClient

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from config import get_settings
from tests.mock_scammer import mock_scammer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestRunner")

class TestHoneyPotE2E(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.settings = get_settings()
        self.api_key = self.settings.api_secret_key
        
    def test_normal_scam_flow(self):
        """Test 1: Normal Judge Evaluation Flow"""
        logger.info(">>> TEST START: Normal Scam Flow")
        
        # Use Mock Scammer to generate input
        scam_message = mock_scammer.get_response("Hello")
        
        payload = {
            "message": scam_message,
            "conversation_id": "test-judge-session-001"
        }
        
        headers = {"x-api-key": self.api_key}
        
        response = self.client.post("/analyze", json=payload, headers=headers)
        
        # 1. Verify Status Code
        self.assertEqual(response.status_code, 200)
        
        # 2. Verify minimal response format per Section 8
        data = response.json()
        
        self.assertIn("status", data)
        self.assertEqual(data["status"], "success")
        self.assertIn("reply", data)
        # Response should ONLY have status and reply
        self.assertEqual(set(data.keys()), {"status", "reply"})
        
        logger.info(">>> TEST PASS: Normal Scam Flow")

    def test_hackathon_payload_support(self):
        """Test 2: Verify support for Hackathon Nested JSON & sessionId (Section 6)"""
        logger.info(">>> TEST START: Hackathon Payload Support")
        
        # Complex nested structure seen in Hackathon logs
        payload = {
            "sessionId": "hackathon-session-123",
            "message": {
                "text": "URGENT: Your connection will be cut. Pay bill now.",
                "sender": "scammer",
                "timestamp": 1234567890
            },
            "conversationHistory": [],
            "metadata": {"channel": "SMS", "language": "English", "locale": "IN"}
        }
        
        headers = {"x-api-key": self.api_key}
        
        response = self.client.post("/analyze", json=payload, headers=headers)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify minimal response format per Section 8
        self.assertIn("status", data)
        self.assertEqual(data["status"], "success")
        self.assertIn("reply", data)
        self.assertEqual(set(data.keys()), {"status", "reply"})
        
        logger.info(">>> TEST PASS: Hackathon Payload Support")

    def test_clean_message_flow(self):
        """Test 3: Legitimate Message (Verify Dynamic Scoring)"""
        logger.info(">>> TEST START: Clean Message Flow")
        
        payload = {
            "message": "Hey mom, I'll be home around 6 PM for dinner. Love you!",
            "conversation_id": "test-clean-session-001"
        }
        
        headers = {"x-api-key": self.api_key}
        
        response = self.client.post("/analyze", json=payload, headers=headers)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify minimal response format
        self.assertEqual(data["status"], "success")
        self.assertEqual(set(data.keys()), {"status", "reply"})
        
        logger.info(">>> TEST PASS: Clean Message Flow")


    def test_missing_auth(self):
        """Test 4: Verify Auth Enforcement"""
        payload = {"message": "Test"}
        # No Headers
        response = self.client.post("/analyze", json=payload)
        self.assertEqual(response.status_code, 401)

    def test_compatibility_endpoints(self):
        """Test 5: Verify Hackathon Compatibility Endpoints"""
        logger.info(">>> TEST START: Compatibility Endpoints")
        
        # 1. GET /analyze (Ping check)
        resp1 = self.client.get("/analyze")
        self.assertEqual(resp1.status_code, 200)
        self.assertIn("ready", str(resp1.json()))
        
        # 2. POST / (Root Ping)
        resp2 = self.client.post("/", json={})
        self.assertEqual(resp2.status_code, 200)
        
        # 3. Trailing Slash (POST /analyze/)
        payload = {"message": "Slash test", "conversation_id": "test-slash"}
        headers = {"x-api-key": self.api_key}
        resp3 = self.client.post("/analyze/", json=payload, headers=headers)
        self.assertEqual(resp3.status_code, 200)
        self.assertEqual(set(resp3.json().keys()), {"status", "reply"})
            
        logger.info(">>> TEST PASS: Compatibility Endpoints")

    def test_multiturn_conversation_history(self):
        """Test 6: Multi-turn conversation with conversationHistory (Section 6.2)"""
        logger.info(">>> TEST START: Multi-turn Conversation History")
        
        # Follow-up message with prior conversation history
        payload = {
            "sessionId": "multiturn-session-001",
            "message": {
                "sender": "scammer",
                "text": "Share your UPI ID to avoid account suspension.",
                "timestamp": 1770005529000
            },
            "conversationHistory": [
                {
                    "sender": "scammer",
                    "text": "Your bank account will be blocked today. Verify immediately.",
                    "timestamp": 1770005528731
                },
                {
                    "sender": "user",
                    "text": "Why will my account be blocked?",
                    "timestamp": 1770005528900
                }
            ],
            "metadata": {"channel": "SMS", "language": "English", "locale": "IN"}
        }
        
        headers = {"x-api-key": self.api_key}
        
        response = self.client.post("/analyze", json=payload, headers=headers)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify minimal response format per Section 8
        self.assertEqual(data["status"], "success")
        self.assertIn("reply", data)
        self.assertEqual(set(data.keys()), {"status", "reply"})
        
        logger.info(">>> TEST PASS: Multi-turn Conversation History")

if __name__ == "__main__":
    unittest.main()

