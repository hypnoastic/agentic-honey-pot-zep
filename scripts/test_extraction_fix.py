import asyncio
import logging
from agents.entity_utils import merge_entities, normalize_entity_value
from utils.prefilter import extract_entities_deterministic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_extraction():
    test_text = "Please forward OTP to +91-9876543210 immediately. Also call me at 9876543210."
    
    print(f"\n--- Testing Text: '{test_text}' ---")
    
    # Step 1: Deterministic extraction
    regex_entities = extract_entities_deterministic(test_text)
    print("Regex Entities (Raw):")
    for k, v in regex_entities.items():
        if v:
            print(f"  - {k}: {[i.get('value') for i in v]}")
            
    # Step 2: Merge (which now includes disambiguation and normalization)
    # Simulate merging with empty to see how it handles the current turn
    merged = merge_entities({}, regex_entities)
    
    print("\nMerged/Normalized/Disambiguated Entities:")
    for k, v in merged.items():
        if v:
            print(f"  - {k}: {[i.get('value') for i in v]}")
            
    # Success markers
    phone_numbers = [i.get('value') for i in merged.get('phone_numbers', [])]
    bank_accounts = [i.get('value') for i in merged.get('bank_accounts', [])]
    
    if len(phone_numbers) == 1 and phone_numbers[0] == "9876543210":
        print("\n✅ SUCCESS: Phone number normalized and deduplicated.")
    else:
        print("\n❌ FAILURE: Phone number normalization/deduplication failed.")
        print(f"   Found: {phone_numbers}")

    if "9876543210" not in bank_accounts:
        print("✅ SUCCESS: Phone number correctly excluded from Bank Accounts.")
    else:
        print("❌ FAILURE: Phone number still present in Bank Accounts.")
        print(f"   Found: {bank_accounts}")

if __name__ == "__main__":
    asyncio.run(test_extraction())
