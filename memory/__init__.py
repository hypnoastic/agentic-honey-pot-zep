"""
Memory module for Agentic Honey-Pot system.
Provides persistent conversational memory using Zep Context AI.
"""

from memory.zep_memory import (
    load_conversation_memory,
    persist_conversation_memory,
    search_similar_scams,
    get_user_profile,
    inject_memory_into_state,
    is_zep_available
)

__all__ = [
    "load_conversation_memory",
    "persist_conversation_memory",
    "search_similar_scams",
    "get_user_profile",
    "inject_memory_into_state",
    "is_zep_available"
]
