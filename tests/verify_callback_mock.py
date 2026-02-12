#!/usr/bin/env python3
import asyncio
import sys
import uuid
import logging
import json
sys.path.insert(0, '.')

from graph.workflow import run_honeypot_workflow, _trigger_guvi_callback_with_retry

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VERIFICATION")

async def test_mock_triggers():
    print("\n" + "="*80)
    print("MOCK STATE VERIFICATION")
    print("="*80)
    
    # CASE A: Planner says JUDGE + GUILTY -> Should trigger
    state_guilty = {
        "planner_action": "judge",
        "judge_verdict": "GUILTY",
        "scam_detected": True,
        "extracted_entities": {"upi_ids": ["test@upi"]},
        "callback_sent": False,
        "conversation_history": [],
        "engagement_count": 5
    }
    print("\nCase A: Planner=judge, Verdict=GUILTY")
    res_a = await _trigger_guvi_callback_with_retry(state_guilty, "mock-session-a")
    print(f"-> Expected: True | Result: {res_a}")

    # CASE B: Planner says END -> Should skip
    state_end = {
        "planner_action": "end",
        "judge_verdict": None,
        "extracted_entities": {"upi_ids": ["test@upi"]},
        "callback_sent": False,
        "conversation_history": [],
        "engagement_count": 5
    }
    print("\nCase B: Planner=end")
    res_b = await _trigger_guvi_callback_with_retry(state_end, "mock-session-b")
    print(f"-> Expected: False | Result: {res_b}")

    # CASE C: Planner says ENGAGE (even with lots of entities) -> Should skip
    state_engage = {
        "planner_action": "engage",
        "judge_verdict": None,
        "extracted_entities": {"upi_ids": ["a@b", "c@d", "e@f"], "bank_accounts": ["123", "456"]},
        "callback_sent": False,
        "conversation_history": [],
        "engagement_count": 2
    }
    print("\nCase C: Planner=engage (5 entities)")
    res_c = await _trigger_guvi_callback_with_retry(state_engage, "mock-session-c")
    print(f"-> Expected: False | Result: {res_c}")

if __name__ == "__main__":
    asyncio.run(test_mock_triggers())
