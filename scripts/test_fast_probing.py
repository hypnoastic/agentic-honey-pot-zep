import asyncio
import logging
from graph.workflow import run_honeypot_workflow
from agents.planner import _determine_verdict

# Setup logging
logging.basicConfig(level=logging.ERROR)

async def test_probing_response():
    print("\n--- TEST 1: Probing Question Verification ---")
    
    # Simulate a scam initiation
    scam_msg = "URGENT: Your connection to SBI will be severed. Update PAN immediately via this link."
    print(f"Input: {scam_msg}")
    
    # We set POSTGRES_ENABLED=false to avoid DB connection issues in this script
    import os
    os.environ["POSTGRES_ENABLED"] = "false"
    import uuid
    cid = str(uuid.uuid4())
    
    try:
        # Run workflow
        result = await run_honeypot_workflow(
            message=scam_msg,
            conversation_id=cid,
            max_engagements=1
        )
        
        response = result.get("agent_response", "")
        # If response is buried in final_response dict
        if isinstance(result, dict) and "agent_response" in result.get("final_response", {}):
             response = result["final_response"]["agent_response"]
             
        print(f"Response: {response}")
        
        # Check for probing indicators
        probing_keywords = ["why", "how", "official", "link", "verify", "call", "branch", "?", "website", "number"]
        is_probing = any(k in response.lower() for k in probing_keywords)
        
        if is_probing:
            print("✅ PASS: Response contains probing/verification questions.")
        else:
            print("❌ FAIL: Response seems passive.")
            
    except Exception as e:
        print(f"Workflow failed: {e}")

async def test_verdict_reasoning():
    print("\n--- TEST 2: Red Flag Reasoning Verification ---")
    
    # Mock specific state with indicators
    mock_state = {
        "scam_detected": True,
        "scam_type": "BANK_IMPERSONATION",
        "scam_indicators": [
            "Urgency (Immediate action required)",
            "Suspicious Link (bit.ly)",
            "Threat (Connection severed)"
        ],
        "behavioral_signals": ["Aggressive pressure"],
        "extracted_entities": {
            "bank_accounts": [],
            "upi_ids": ["fraud@upi"],
            "phishing_urls": ["http://bit.ly/fake"]
        }
    }
    
    # Call the verdict logic directly
    verdict, confidence, reasoning = _determine_verdict(
        state=mock_state,
        entities=mock_state["extracted_entities"],
        high_value=2,
        distinct_types=2
    )
    
    print(f"Verdict: {verdict}")
    print(f"Reasoning:\n{reasoning}")
    
    # Verify Red Flags are present in text
    if "RED FLAGS: Urgency" in reasoning and "Suspicious Link" in reasoning:
        print("✅ PASS: Specific red flags found in reasoning.")
    else:
        print("❌ FAIL: Red flags missing from reasoning.")

async def main():
    await test_probing_response()
    await test_verdict_reasoning()

if __name__ == "__main__":
    asyncio.run(main())
