"""
Failure Injection Test for Agentic Honey-Pot.
Verifies that the system returns valid JSON even when internal components crash.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from config import get_settings

class TestFailures(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.settings = get_settings()
        self.api_key = self.settings.api_secret_key
        
    def test_zep_memory_failure(self):
        """Test 1: Simulating Zep Memory Crash"""
        print("\n>>> TEST: Zep Memory Crash Injection")
        
        # Mocking run_honeypot_analysis to simulate a crash inside the workflow
        # We patch at the module level where it is imported in main.py
        with patch('main.run_honeypot_analysis') as mock_workflow:
            mock_workflow.side_effect = Exception("Simulated Zep Connection Timeout")
            
            payload = {"message": "Hello"}
            headers = {"x-api-key": self.api_key}
            
            response = self.client.post("/analyze", json=payload, headers=headers)
            
            # Should NOT be 500
            self.assertEqual(response.status_code, 200)
            
            data = response.json()
            print(f"Fallback Response: {data}")
            
            # Verify Safe Fallback Structure
            self.assertFalse(data["is_scam"])
            self.assertEqual(data["confidence_score"], 0.0)
            # The fallback uses a generic message for safety
            self.assertIn("System fail-safe triggered", str(data))
            
            # Check validation of fields
            self.assertIsInstance(data["extracted_entities"], dict)

    def test_corrupted_workflow_return(self):
        """Test 2: Workflow returns garbage data"""
        print("\n>>> TEST: Corrupted Workflow Return")
        
        with patch('main.run_honeypot_analysis') as mock_workflow:
            # Return something that is NOT a dict or missing fields
            mock_workflow.return_value = "This is not a dict"
            
            payload = {"message": "Hello"}
            headers = {"x-api-key": self.api_key}
            
            response = self.client.post("/analyze", json=payload, headers=headers)
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            # Should fallback because it failed to parse "This is not a dict"
            self.assertFalse(data["is_scam"])

if __name__ == "__main__":
    unittest.main()
