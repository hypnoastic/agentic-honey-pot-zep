import asyncio
import unittest
from unittest.mock import patch
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.fact_checker import verify_claim

class TestFactCheckerHardening(unittest.IsolatedAsyncioTestCase):
    @patch("agents.fact_checker.search_serper")
    async def test_legit(self, mock_search):
        mock_search.return_value = [{"title": "PM Kisan", "snippet": "Official", "link": "https://pmkisan.gov.in/", "position": 1}]
        result = await verify_claim({"text": "PM Kisan", "type": "scheme"})
        print(f"Legit: {result['status']} {result['confidence']}")
        self.assertEqual(result["status"], "POSSIBLY_LEGITIMATE")

    @patch("agents.fact_checker.search_serper")
    async def test_scam(self, mock_search):
        mock_search.return_value = [{"title": "Scam", "snippet": "Fake link", "link": "https://fake.site", "position": 1}]
        result = await verify_claim({"text": "PM Kisan Free", "type": "scheme"})
        print(f"Scam: {result['status']} {result['confidence']}")
        self.assertEqual(result["status"], "LIKELY_SCAM")

if __name__ == "__main__":
    unittest.main()
