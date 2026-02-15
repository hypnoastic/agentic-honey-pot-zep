import sys
import os
import re

# Add parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.prefilter import extract_entities_deterministic, ENTITY_PATTERNS

text = "Email me at scammer@fake.com"
print(f"Testing text: '{text}'")

# Test Regex directly
email_pattern = ENTITY_PATTERNS.get("email_addresses", [])
print(f"Email Patterns: {email_pattern}")

for pat in email_pattern:
    matches = re.findall(pat, text, re.IGNORECASE)
    print(f"Regex '{pat}' matches: {matches}")

# Test extraction function
entities = extract_entities_deterministic(text)
print(f"Extracted Entities: {entities}")
