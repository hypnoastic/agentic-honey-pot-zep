
import unittest
import asyncio
import json
import uuid
import time
import logging
from httpx import AsyncClient, ASGITransport
from main import app, settings
from memory.postgres_memory import init_db_pool, _get_pool

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IntegrationTest")

# Constants
API_KEY = settings.api_secret_key
HEADERS = {"x-api-key": API_KEY}
BASE_URL = "http://test"

class TestHoneyPotIntegration(unittest.IsolatedAsyncioTestCase):
    """
    Production-Grade Unified Integration Test Suite.
    Covers Scenarios A-E: Normal, Early Victory, Safe Exit, Concurrency.
    Uses native unittest.IsolatedAsyncioTestCase to avoid pytest-asyncio dependency issues.
    """
    
    async def asyncSetUp(self):
        """Initialize DB pool before each test."""
        await init_db_pool()
        self.pool = await _get_pool()
        if not self.pool:
            self.fail("DB Pool failed to initialize")

    async def asyncTearDown(self):
        """Close DB pool after each test."""
        # In a real app we might not close it to reuse, but for isolation we can.
        # Actually, let's keep it open for performance, or close if strict isolation needed.
        # For now, we trust the pool manager.
        pass

    async def test_scenario_a_normal_flow(self):
        """
        CASE A: Normal Scam Flow (Engage Path)
        - DB Handshake, Embedding Generation (Batch), Parallel Logic, Persistence.
        """
        session_id = str(uuid.uuid4())
        logger.info(f"--- START SCENARIO A: {session_id} ---")
        
        payload = {
            "conversation_id": session_id,
            "message": {
                "sender": "scammer",
                "text": "Your bank account will be blocked today. Verify immediately.",
                "timestamp": int(time.time() * 1000)
            },
            "conversationHistory": [],
            "metadata": {"channel": "SMS", "language": "English", "locale": "IN"}
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as ac:
            start_time = time.time()
            response = await ac.post("/analyze", json=payload, headers=HEADERS)
            intake_duration = time.time() - start_time
        
        self.assertEqual(response.status_code, 200, f"Failed: {response.text}")
        data = response.json()
        
        logger.info(f"Scenario A Response: {json.dumps(data, indent=2)}")
        logger.info(f"Intake Duration: {intake_duration:.4f}s")

        # Verify Response Structure
        self.assertEqual(data["status"], "success")
        reply = data.get("reply")
        self.assertIsNotNone(reply, "Reply should not be None")
        self.assertTrue(len(reply) > 0, "Reply should not be empty")
        # We expect scam detection to be true given the "blocked account" keyword
        self.assertTrue(data["scam_detected"], "Scam should be detected")
        
        # Verify Persistence (Async Wait)
        await asyncio.sleep(2.0)
        
        async with self.pool.acquire() as conn:
            # Check Session
            meta = await conn.fetchval("SELECT metadata FROM sessions WHERE session_id = $1", session_id)
            meta = json.loads(meta)
            self.assertTrue(meta["scam_detected"])
            
            # Check Messages (Embeddings)
            count = await conn.fetchval("SELECT COUNT(*) FROM messages WHERE session_id = $1", session_id)
            self.assertGreaterEqual(count, 1)

    async def test_scenario_b_early_victory(self):
        """
        CASE B: Early Victory (Immediate Judge)
        - High-Value Entities -> Judge -> Callback.
        """
        session_id = str(uuid.uuid4())
        logger.info(f"--- START SCENARIO B: {session_id} ---")
        
        text = "Urgent! Transfer to UPI: scammer@upi. Click http://malicious.com now!"
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as ac:
            start_time = time.time()
            response = await ac.post("/analyze", json={
                "conversation_id": session_id,
                "message": text
            }, headers=HEADERS)
            duration = time.time() - start_time
        
        data = response.json()
        logger.info(f"Scenario B Duration: {duration:.4f}s")
        
        self.assertTrue(data["scam_detected"])
        entities = data.get("extracted_entities", {})
        upi_ids = [e.get("value") if isinstance(e, dict) else e for e in entities.get("upi_ids", [])]
        self.assertIn("scammer@upi", upi_ids)

    async def test_scenario_c_non_scam(self):
        """
        CASE C: Non-Scam Safe Exit
        - No engagement, no scam flag.
        """
        # Scenario C: Non-Scam Safe Exit
        # Use a clearly benign message to ensure negative classification
        session_id = str(uuid.uuid4())
        logger.info(f"--- START SCENARIO C: {session_id} ---")
        message = "System test: legitimate inquiry about weather."
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as ac:
            response = await ac.post("/analyze", json={
                "conversation_id": session_id,
                "message": message
            }, headers=HEADERS)
        
        data = response.json()
        self.assertFalse(data["scam_detected"])
        
        # Verify NO scam alert in DB
        await asyncio.sleep(1.0)
        async with self.pool.acquire() as conn:
            meta_json = await conn.fetchval("SELECT metadata FROM sessions WHERE session_id = $1", session_id)
            if meta_json:
                meta = json.loads(meta_json)
                self.assertFalse(meta.get("scam_detected", False))

    async def test_scenario_d_concurrency_same_session(self):
        """
        CASE D: Concurrent Same Session Messages
        - Race condition check.
        """
        session_id = str(uuid.uuid4())
        logger.info(f"--- START SCENARIO D: {session_id} ---")
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as ac:
            async def send_req(msg):
                return await ac.post("/analyze", json={
                    "conversation_id": session_id,
                    "message": msg
                }, headers=HEADERS)
            
            # Launch 2 simultaneous requests
            t1 = asyncio.create_task(send_req("Message 1"))
            t2 = asyncio.create_task(send_req("Message 2"))
            
            results = await asyncio.gather(t1, t2)
            
            self.assertEqual(results[0].status_code, 200)
            self.assertEqual(results[1].status_code, 200)

    async def test_scenario_e_concurrency_diff_sessions(self):
        """
        CASE E: Concurrent Different Sessions (Throughput)
        - Throughput check.
        """
        logger.info("--- START SCENARIO E ---")
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as ac:
            async def run_session(i):
                sid = str(uuid.uuid4())
                start = time.time()
                resp = await ac.post("/analyze", json={
                    "conversation_id": sid,
                    "message": f"Scam attempt {i}: Verify bank account."
                }, headers=HEADERS)
                dur = time.time() - start
                return dur, resp.status_code

            # Run 5 parallel sessions
            tasks = [run_session(i) for i in range(5)]
            results = await asyncio.gather(*tasks)
            
            for dur, status in results:
                self.assertEqual(status, 200)
                logger.info(f"Parallel Task Duration: {dur:.4f}s")
