import re
from typing import Dict, List, Any


def normalize_entity_value(value: str, entity_type: str) -> str:
    """
    Standardize entity values to prevent duplicates (e.g., +91-9876543210 -> 9876543210).
    """
    if not value:
        return ""
    
    # Strip whitespace for all
    clean_value = value.strip()
    
    if entity_type == "phone_numbers":
        # Remove all non-digits
        digits = re.sub(r"\D", "", clean_value)
        # Handle Indian 10-digit numbers (remove leading 91, 0, +91)
        if len(digits) > 10 and (digits.startswith("91") or digits.startswith("091")):
             # Potential +91 or 091 prefix
             if digits.startswith("091"):
                 digits = digits[3:]
             else:
                 digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        return digits
    
    if entity_type == "bank_accounts":
        # Remove all non-digits and spaces
        return re.sub(r"\D", "", clean_value)
    
    if entity_type in ["case_ids", "policy_numbers", "order_numbers"]:
        # Strip common labels but LEAVE the actual ID structure intact
        # Don't force uppercase, allow hyphens
        clean_val = clean_value
        
        # Only strip labels if they are at the very beginning and followed by a space/colon/hyphen
        clean_val = re.sub(r'(?i)^(?:case|complaint|ticket|ref|reference|policy|pol|order|ord|inv|txn)\s*(?:no\.?|number|id|#)?[:\-\s]+', '', clean_val)
        
        # Clean external non-alphanumeric except hyphens
        clean_val = re.sub(r'^[^a-zA-Z0-9]+|[^a-zA-Z0-9\-]+$', '', clean_val)
        
        # Block common extraction noise words (case-insensitive check)
        NOISE_WORDS = {
            "ERENCE", "BENEFITS", "NUMBER", "ERENCES", "DETAILS", "PROCESS", 
            "PENDING", "VALUE", "STATUS", "REFERENCE", "TYPE", "INFORMATION", 
            "CONFIRMATION", "SUPPORT", "REFID", "CASEID", "ORDERID", "POLICYID",
            "REFNO", "CASENO", "ORDERNO", "POLICYNO", "REFNUMBER", "CASENUMBER",
            "ORDERNUMBER", "POLICYNUMBER", "REF_ID", "CASE_ID", "ORDER_ID", "POLICY_ID",
            "ID", "IDS", "CODE", "CODES", "NUM", "NUMS", "EXTRACT", "VERIFY",
            "DATA", "INFO", "USER", "CUSTOMER", "CLIENT", "AGENT", "ADMIN",
            "TRANS", "TRANSACTION", "PAYMENT", "AMOUNT", "BILL", "RECEIPT", "INVOICE"
        }
        
        if clean_val.upper() in NOISE_WORDS:
            return ""
            
        if len(clean_val) < 4 and not any(c.isdigit() for c in clean_val):
            return ""
            
        return clean_val
        
    return clean_value


def disambiguate_entities(entities: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
    """
    Prevent one value from being assigned to multiple conflicting types.
    Priority: Phone Numbers > Bank Accounts (if 10 digits).
    """
    phone_vals = {normalize_entity_value(e.get("value") if isinstance(e, dict) else e, "phone_numbers") 
                  for e in entities.get("phone_numbers", [])}
    
    # Filter bank accounts that are actually phone numbers
    if "bank_accounts" in entities:
        new_bank_list = []
        for item in entities["bank_accounts"]:
            val = normalize_entity_value(item.get("value") if isinstance(item, dict) else item, "bank_accounts")
            # If it looks like a phone number (10 digits) and matches an existing phone number, skip it
            if len(val) == 10 and val in phone_vals:
                continue
            new_bank_list.append(item)
        entities["bank_accounts"] = new_bank_list
        
    return entities


def merge_entities(entities_a: Dict, entities_b: Dict) -> Dict:
    """
    Merge two entity dictionaries, combining lists and removing duplicates.
    Handles both dict format ({"value": "..."}) and string format.
    Applies normalization and disambiguation.
    """
    merged = {}
    all_keys = set(entities_a.keys()) | set(entities_b.keys())
    
    for key in all_keys:
        list_a = entities_a.get(key, [])
        list_b = entities_b.get(key, [])
        
        # Ensure both are lists
        if not isinstance(list_a, list):
            list_a = []
        if not isinstance(list_b, list):
            list_b = []
        
        # Combine lists
        combined_items = list_a + list_b
        
        # Deduplicate and normalize
        seen_normalized = set()
        deduplicated = []
        for item in combined_items:
            raw_val = item.get("value") if isinstance(item, dict) else item
            norm_val = normalize_entity_value(raw_val, key)
            
            if norm_val and norm_val not in seen_normalized:
                seen_normalized.add(norm_val)
                # Ensure it's in dict format for consistency
                if isinstance(item, dict):
                    item["value"] = norm_val # Use normalized value
                    deduplicated.append(item)
                else:
                    deduplicated.append({"value": norm_val, "confidence": 1.0, "source": "explicit"})
        
        merged[key] = deduplicated
    
    # Final pass: disambiguate types
    return disambiguate_entities(merged)
