from typing import Dict


def merge_entities(entities_a: Dict, entities_b: Dict) -> Dict:
    """
    Merge two entity dictionaries, combining lists and removing duplicates.
    Handles both dict format ({"value": "..."}) and string format.
    
    Args:
        entities_a: First entity dict (e.g., prior_entities from memory)
        entities_b: Second entity dict (e.g., newly extracted entities)
        
    Returns:
        Merged entity dict with deduplicated lists
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
        
        # Extract values for deduplication (handle both dict and string formats)
        def extract_value(item):
            if isinstance(item, dict):
                return item.get("value", str(item))
            return str(item)
        
        # Combine lists
        combined_items = list_a + list_b
        
        # Deduplicate by value
        seen_values = set()
        deduplicated = []
        for item in combined_items:
            value = extract_value(item)
            if value and value not in seen_values:
                seen_values.add(value)
                deduplicated.append(item)
        
        merged[key] = deduplicated
    
    return merged
