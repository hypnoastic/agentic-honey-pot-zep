import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.intelligence_extraction import intelligence_extraction_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_extraction_hardening():
    # 1. Turn 1: Scammer sends UPI
    state = {
        "original_message": "Pay 500 to sbi@upi",
        "conversation_history": [
            {"role": "scammer", "message": "Pay 500 to sbi@upi"}
        ],
        "extracted_entities": {}
    }

    logger.info("--- TURN 1: Initial Extraction ---")
    result = await intelligence_extraction_agent(state)
    state.update(result)
    
    # Verify result 1
    upi_vals = [e["value"] for e in state["extracted_entities"].get("upi_ids", [])]
    logger.info(f"Entities after T1: {upi_vals}")
    assert "sbi@upi" in upi_vals

    # 2. Turn 2: Scammer sends Bank info
    logger.info("--- TURN 2: Incremental Merge ---")
    state["conversation_history"].append({"role": "honeypot", "message": "Ok, what is the bank account?"})
    state["conversation_history"].append({"role": "scammer", "message": "Acc: 1234567890"})
    
    # This should only scan "Acc: 1234567890" but merge with "sbi@upi"
    result = await intelligence_extraction_agent(state)
    state.update(result)
    
    # Verify Merge
    all_upi = [e["value"] for e in state["extracted_entities"].get("upi_ids", [])]
    all_bank = [e["value"] for e in state["extracted_entities"].get("bank_accounts", [])]
    
    logger.info(f"Final UPIs: {all_upi}")
    logger.info(f"Final Banks: {all_bank}")
    
    assert "sbi@upi" in all_upi
    assert "1234567890" in all_bank
    
    logger.info("✅ SUCCESS: Phase 10 Extraction Hardening Verified!")

if __name__ == "__main__":
    asyncio.run(test_extraction_hardening())
