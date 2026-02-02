"""
Mock Scammer API for Testing.
Generates deterministic scam responses to drive the engagement loop during tests.
"""

import random

class MockScammer:
    def __init__(self):
        self.responses = [
            "Hello sir, I am calling from bank. You have pending KYC.",
            "Yes, please send me the OTP specifically.",
            "Do not worry, just click the link I sent.",
            "Sir, if you do not pay, your account is blocked.",
            "I am not scammer, I am official agent."
        ]
        
    def get_response(self, message: str) -> str:
        """Get a response to the victim's message."""
        # Simple logic: return a random scam phrase
        return random.choice(self.responses)

# Singleton instance
mock_scammer = MockScammer()
