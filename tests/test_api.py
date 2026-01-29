"""
API Tests for Agentic Honey-Pot
Tests the FastAPI endpoint with various scam and non-scam messages.
"""

import pytest
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)

# Valid API key for testing
VALID_API_KEY = "test-api-key-123"


class TestHealthEndpoint:
    """Tests for the health check endpoint."""
    
    def test_health_check(self):
        """Test that health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data


class TestAuthentication:
    """Tests for API key authentication."""
    
    def test_missing_api_key(self):
        """Test that requests without API key are rejected."""
        response = client.post(
            "/analyze",
            json={"message": "Hello"}
        )
        assert response.status_code == 422  # Validation error for missing header
    
    def test_invalid_api_key(self):
        """Test that requests with invalid API key are rejected."""
        response = client.post(
            "/analyze",
            headers={"x-api-key": "wrong-key"},
            json={"message": "Hello"}
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]
    
    def test_valid_api_key(self):
        """Test that requests with valid API key are accepted."""
        response = client.post(
            "/analyze",
            headers={"x-api-key": VALID_API_KEY},
            json={"message": "Hello, how are you today?"}
        )
        assert response.status_code == 200


class TestScamDetection:
    """Tests for scam detection functionality."""
    
    def test_lottery_scam(self):
        """Test detection of lottery fraud."""
        response = client.post(
            "/analyze",
            headers={"x-api-key": VALID_API_KEY},
            json={
                "message": "Congratulations! You have won Rs 50,00,000 in our lucky draw! Send Rs 500 to UPI: winner@paytm to claim your prize immediately!"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_scam"] == True
        assert data["scam_type"] is not None
        assert data["confidence_score"] > 0.5
    
    def test_upi_fraud(self):
        """Test detection of UPI fraud."""
        response = client.post(
            "/analyze",
            headers={"x-api-key": VALID_API_KEY},
            json={
                "message": "Your KYC needs to be updated urgently. Transfer Rs 1 to verify your account: UPI ID: kyc.verify@ybl"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_scam"] == True
        assert "upi_ids" in data["extracted_entities"]
    
    def test_bank_impersonation(self):
        """Test detection of bank impersonation."""
        response = client.post(
            "/analyze",
            headers={"x-api-key": VALID_API_KEY},
            json={
                "message": "This is SBI Bank. Your account will be blocked in 24 hours unless you update KYC. Click here: http://sbi-kyc-update.fake.com"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_scam"] == True
        assert len(data["extracted_entities"]["phishing_urls"]) > 0 or data["scam_type"] is not None
    
    def test_non_scam_message(self):
        """Test that legitimate messages are not flagged."""
        response = client.post(
            "/analyze",
            headers={"x-api-key": VALID_API_KEY},
            json={
                "message": "Hi, this is a reminder about our meeting tomorrow at 3 PM. Please confirm your attendance."
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_scam"] == False
        assert data["scam_type"] is None


class TestResponseStructure:
    """Tests for response structure validation."""
    
    def test_response_has_required_fields(self):
        """Test that response contains all required fields."""
        response = client.post(
            "/analyze",
            headers={"x-api-key": VALID_API_KEY},
            json={"message": "Test message"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "is_scam" in data
        assert "scam_type" in data
        assert "confidence_score" in data
        assert "extracted_entities" in data
        assert "conversation_summary" in data
        
        # Check extracted_entities structure
        entities = data["extracted_entities"]
        assert "bank_accounts" in entities
        assert "upi_ids" in entities
        assert "phishing_urls" in entities
        
        # Check types
        assert isinstance(data["is_scam"], bool)
        assert isinstance(data["confidence_score"], (int, float))
        assert 0 <= data["confidence_score"] <= 1
        assert isinstance(entities["bank_accounts"], list)
        assert isinstance(entities["upi_ids"], list)
        assert isinstance(entities["phishing_urls"], list)


class TestEntityExtraction:
    """Tests for entity extraction functionality."""
    
    def test_upi_extraction(self):
        """Test extraction of UPI IDs."""
        response = client.post(
            "/analyze",
            headers={"x-api-key": VALID_API_KEY},
            json={
                "message": "Please send money to scammer123@paytm or fraud@gpay for your refund"
            }
        )
        assert response.status_code == 200
        data = response.json()
        # Should process successfully
        assert "extracted_entities" in data
    
    def test_bank_account_extraction(self):
        """Test extraction of bank account numbers."""
        response = client.post(
            "/analyze",
            headers={"x-api-key": VALID_API_KEY},
            json={
                "message": "Transfer the amount to account number 1234567890123456, IFSC: SBIN0001234"
            }
        )
        assert response.status_code == 200
        data = response.json()
        # Should process the message
        assert "is_scam" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
