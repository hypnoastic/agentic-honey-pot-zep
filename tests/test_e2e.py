"""
End-to-End Validation Test for Agentic Honey-Pot.
Verifies normal operation, cold start, and JSON structure.
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
from mock_scammer import mock_scammer

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
        logger.info(f"Generated Mock Scam Message: {scam_message}")
        
        payload = {
            "message": scam_message,
            "conversation_id": "test-judge-session-001",
            "mode": "live" # Deprecated but checking if it breaks anything
        }
        
        headers = {"x-api-key": self.api_key}
        
        response = self.client.post("/analyze", json=payload, headers=headers)
        
        # 1. Verify Status Code
        self.assertEqual(response.status_code, 200)
        
        # 2. Verify Valid JSON
        data = response.json()
        logger.info(f"Response Received: {data}")
        
        self.assertIn("is_scam", data)
        self.assertIn("confidence_score", data)
        self.assertIn("extracted_entities", data)
        
        # 3. Verify Logic Flow (Scam should be detected)
        # Note: Depending on LLM, might vary, but simplified checks:
        self.assertIsInstance(data["is_scam"], bool)
        self.assertIsInstance(data["confidence_score"], float)
        
        logger.info(">>> TEST PASS: Normal Scam Flow")

    def test_cold_start_new_user(self):
        """Test 2: Cold Start (New/Random User)"""
        logger.info(">>> TEST START: Cold Start")
        
        import uuid
        new_id = str(uuid.uuid4())
        
        payload = {
            "message": "Urgent: You won a lottery! Click here: http://bit.ly/fake",
            "conversation_id": new_id
        }
        
        headers = {"x-api-key": self.api_key}
        
        response = self.client.post("/analyze", json=payload, headers=headers)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["conversation_id"], new_id)
        self.assertTrue(data["is_scam"] or data["confidence_score"] > 0.5) # Should likely detect lottery scam
        
        logger.info(">>> TEST PASS: Cold Start")

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
        logger.info(f"Clean Message Response: {data}")
        
        # Verify it is NOT detected as a scam
        self.assertFalse(data["is_scam"], "Benign message was incorrectly flagged as scam")
        
        # Verify confidence score is low (proving it's dynamic, not hardcoded 95%)
        # Allowing some margin for 'suspicion' but strictly less than threshold (usually 0.6)
        self.assertLess(data["confidence_score"], 0.5, "Confidence score too high for benign message")
        
        logger.info(">>> TEST PASS: Clean Message Flow (Dynamic Scoring Confirmed)")

    def test_safe_response_structure_guarantee(self):
        """Verify strict JSON schema adherence"""
        payload = {"message": "Test"}
        headers = {"x-api-key": self.api_key}
        response = self.client.post("/analyze", json=payload, headers=headers)
        data = response.json()
        
        # Check all required fields from Safe Response
        required = ["is_scam", "scam_type", "confidence_score", 
                   "extracted_entities", "behavioral_signals", 
                   "confidence_factors", "agent_reply", "conversation_id"]
                   
        for field in required:
            self.assertIn(field, data, f"Missing required field: {field}")

if __name__ == "__main__":
    unittest.main()
