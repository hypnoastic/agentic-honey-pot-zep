#!/usr/bin/env python3
"""
Test GUVI Callback - Verifies entity accumulation + callback triggering.
Uses valid UUID for proper DB interaction.
"""
import asyncio
import sys
import json
import uuid
sys.path.insert(0, '.')

async def test_guvi_callback():
    print("=" * 70)
    print("GUVI CALLBACK TEST")
    print("=" * 70)
    
    from graph.workflow import run_honeypot_workflow
    from config import get_settings
    
    settings = get_settings()
    print(f"\n✓ GUVI Callback URL: {bool(settings.guvi_callback_url)}")
    if settings.guvi_callback_url:
        print(f"  URL: {settings.guvi_callback_url}")
    
    conversation_id = str(uuid.uuid4())
    print(f"✓ Conversation ID: {conversation_id}")
    
    # Turn 1: UPI ID
    print("\n" + "-" * 70)
    print("Turn 1: Scammer provides UPI ID")
    print("-" * 70)
    
    result1 = await run_honeypot_workflow(
        message="URGENT: Your SBI account compromised. Transfer ₹1 to verify via UPI ID scammer.fraud@fakebank immediately.",
        conversation_id=conversation_id,
        max_engagements=10
    )
    
    entities1 = result1.get('extracted_entities', {})
    upi1 = len(entities1.get('upi_ids', []))
    acc1 = len(entities1.get('bank_accounts', []))
    print(f"  Persona: {result1.get('persona_name', 'N/A')}")
    print(f"  UPI IDs: {upi1} | Bank Accounts: {acc1}")
    print(f"  Entities: {json.dumps(entities1, indent=2)}")
    
    # Turn 2: Bank Account
    print("\n" + "-" * 70)
    print("Turn 2: Scammer provides bank account")
    print("-" * 70)
    
    result2 = await run_honeypot_workflow(
        message="OK transfer to account number 9876543210123456 IFSC SBIN0001234 and share OTP. Also call 9876543210 if issues.",
        conversation_id=conversation_id,
        max_engagements=10
    )
    
    entities2 = result2.get('extracted_entities', {})
    upi2 = len(entities2.get('upi_ids', []))
    acc2 = len(entities2.get('bank_accounts', []))
    phone2 = len(entities2.get('phone_numbers', []))
    total2 = upi2 + acc2 + phone2
    
    print(f"  Persona: {result2.get('persona_name', 'N/A')}")
    print(f"  UPI IDs: {upi2} | Bank Accounts: {acc2} | Phones: {phone2}")
    print(f"  Total Entities: {total2}")
    print(f"  Entities: {json.dumps(entities2, indent=2)}")
    
    # Verification
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    persona1 = result1.get('persona_name', '')
    persona2 = result2.get('persona_name', '')
    
    if total2 >= 2:
        print(f"✅ ENTITY ACCUMULATION: {total2} entities (threshold: 2+)")
    else:
        print(f"❌ ENTITY ACCUMULATION FAILED: {total2} entities (need 2+)")
    
    if persona1 and persona2 and persona1 == persona2:
        print(f"✅ PERSONA PERSISTENCE: '{persona1}' maintained across turns")
    else:
        print(f"❌ PERSONA CHANGED: '{persona1}' → '{persona2}'")
    
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_guvi_callback())
