"""
Zep Context AI Memory Integration
Provides persistent conversational memory and intelligence context for the honeypot system.
Uses Zep Cloud SDK with User, Thread, and Graph APIs per official documentation.
"""

import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Zep client singleton
_zep_client = None

# Default user for honeypot system
HONEYPOT_USER_ID = "honeypot-system"
HONEYPOT_USER_NAME = "Honeypot Agent"


def _get_zep_client():
    """Get or create Zep client."""
    global _zep_client
    if _zep_client is None and settings.zep_api_key and settings.zep_enabled:
        try:
            from zep_cloud.client import Zep
            _zep_client = Zep(api_key=settings.zep_api_key)
            logger.info("Zep client initialized successfully")
            
            # Ensure honeypot user exists
            _ensure_honeypot_user()
        except Exception as e:
            logger.warning(f"Failed to initialize Zep client: {e}")
            _zep_client = None
    return _zep_client


def _ensure_honeypot_user():
    """Ensure the honeypot system user exists in Zep."""
    global _zep_client
    if _zep_client is None:
        return
    
    try:
        # Try to get the user first
        _zep_client.user.get(user_id=HONEYPOT_USER_ID)
        logger.debug(f"Honeypot user {HONEYPOT_USER_ID} already exists")
    except Exception:
        # User doesn't exist, create it
        try:
            _zep_client.user.add(
                user_id=HONEYPOT_USER_ID,
                first_name="Honeypot",
                last_name="Agent",
                email="honeypot@system.local"
            )
            logger.info(f"Created Zep user: {HONEYPOT_USER_ID}")
        except Exception as e:
            logger.warning(f"Could not create honeypot user: {e}")


def _ensure_scammer_user(scammer_id: str) -> str:
    """Ensure a scammer user exists in Zep for tracking."""
    client = _get_zep_client()
    if not client:
        return scammer_id
    
    try:
        client.user.get(user_id=scammer_id)
    except Exception:
        try:
            client.user.add(
                user_id=scammer_id,
                first_name="Scammer",
                last_name=scammer_id[:8]
            )
            logger.debug(f"Created scammer user: {scammer_id}")
        except Exception as e:
            logger.debug(f"Could not create scammer user: {e}")
    
    return scammer_id


async def load_conversation_memory(conversation_id: str) -> Dict[str, Any]:
    """
    Load prior conversation context from Zep using thread API.
    
    Args:
        conversation_id: Unique identifier for the conversation thread
        
    Returns:
        Dictionary containing prior context to inject into LangGraph state
    """
    client = _get_zep_client()
    if not client:
        return {}
    
    memory_context = {
        "prior_messages": [],
        "prior_entities": {
            "bank_accounts": [],
            "upi_ids": [],
            "phishing_urls": []
        },
        "prior_scam_types": [],
        "behavioral_signals": [],
        "conversation_summary": "",
        "zep_context": ""
    }
    
    try:
        # Get user context for the thread (includes summary and relevant facts)
        try:
            user_context = client.thread.get_user_context(thread_id=conversation_id)
            if user_context and hasattr(user_context, 'context'):
                memory_context["zep_context"] = user_context.context or ""
                memory_context["conversation_summary"] = user_context.context or ""
                logger.info(f"Loaded Zep context for thread {conversation_id}")
        except Exception as e:
            logger.debug(f"No user context available: {e}")
        
        # Get thread messages for prior conversation history
        try:
            thread = client.thread.get(thread_id=conversation_id)
            if thread:
                # Get messages from the thread
                messages = client.thread.message.list(thread_id=conversation_id)
                if messages:
                    for msg in messages:
                        memory_context["prior_messages"].append({
                            "role": msg.role if hasattr(msg, 'role') else "user",
                            "content": msg.content if hasattr(msg, 'content') else str(msg),
                            "name": msg.name if hasattr(msg, 'name') else None,
                            "timestamp": str(msg.created_at) if hasattr(msg, 'created_at') else None
                        })
                
                # Get thread metadata for extracted entities
                if hasattr(thread, 'metadata') and thread.metadata:
                    metadata = thread.metadata
                    if isinstance(metadata, dict):
                        memory_context["prior_entities"] = metadata.get("entities", memory_context["prior_entities"])
                        memory_context["prior_scam_types"] = metadata.get("scam_types", [])
                        memory_context["behavioral_signals"] = metadata.get("signals", [])
        except Exception as e:
            logger.debug(f"Thread not found or no messages: {e}")
        
        if memory_context["prior_messages"]:
            logger.info(f"Loaded {len(memory_context['prior_messages'])} prior messages from Zep")
        
    except Exception as e:
        error_str = str(e).lower()
        if "not found" not in error_str and "404" not in error_str:
            logger.debug(f"No prior Zep memory for {conversation_id}: {e}")
    
    return memory_context


async def persist_conversation_memory(
    conversation_id: str,
    state: Dict[str, Any],
    is_final: bool = False
) -> bool:
    """
    Persist conversation turns and extracted intelligence to Zep.
    
    Args:
        conversation_id: Unique identifier for the conversation thread
        state: Current LangGraph state with conversation data
        is_final: Whether this is the final state
        
    Returns:
        Success status
    """
    client = _get_zep_client()
    if not client:
        return False
    
    try:
        from zep_cloud.types import Message
        
        # Ensure thread exists (create with honeypot user if not)
        thread_exists = False
        try:
            client.thread.get(thread_id=conversation_id)
            thread_exists = True
        except Exception:
            # Create new thread linked to honeypot user
            try:
                client.thread.create(
                    thread_id=conversation_id,
                    user_id=HONEYPOT_USER_ID
                )
                thread_exists = True
                logger.info(f"Created Zep thread: {conversation_id}")
            except Exception as e:
                logger.debug(f"Could not create thread: {e}")
        
        if not thread_exists:
            return False
        
        # Prepare messages to add
        messages = []
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Add original scam message as scammer message
        original_msg = state.get("original_message", "")
        if original_msg:
            messages.append(Message(
                created_at=timestamp,
                name="Scammer",
                role="user",
                content=original_msg
            ))
        
        # Add conversation history with proper naming
        conversation_history = state.get("conversation_history", [])
        for i, turn in enumerate(conversation_history):
            role = turn.get("role", "user")
            name = HONEYPOT_USER_NAME if role == "honeypot" else "Scammer"
            zep_role = "assistant" if role == "honeypot" else "user"
            
            messages.append(Message(
                created_at=timestamp,
                name=name,
                role=zep_role,
                content=turn.get("message", "")
            ))
        
        # Add messages to thread
        if messages:
            try:
                client.thread.add_messages(
                    thread_id=conversation_id,
                    messages=messages
                )
                logger.info(f"Added {len(messages)} messages to Zep thread {conversation_id}")
            except Exception as e:
                logger.debug(f"Could not add messages: {e}")
        
        # Add extracted intelligence to graph as business data
        if is_final and state.get("scam_detected"):
            await _add_intelligence_to_graph(client, conversation_id, state)
        
        return True
        
    except Exception as e:
        logger.warning(f"Error persisting to Zep: {e}")
        return False


async def _add_intelligence_to_graph(client, conversation_id: str, state: Dict[str, Any]):
    """Add extracted scam intelligence to Zep graph as business data."""
    try:
        entities = state.get("extracted_entities", {})
        
        # Build intelligence event data
        intelligence_data = {
            "event_type": "scam_detected",
            "conversation_id": conversation_id,
            "scam_type": state.get("scam_type"),
            "confidence_score": state.get("confidence_score", 0.0),
            "bank_accounts": entities.get("bank_accounts", []),
            "upi_ids": entities.get("upi_ids", []),
            "phishing_urls": entities.get("phishing_urls", []),
            "scam_indicators": state.get("scam_indicators", []),
            "persona_used": state.get("persona_name"),
            "engagement_turns": state.get("engagement_count", 0),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Add to graph
        client.graph.add(
            user_id=HONEYPOT_USER_ID,
            type="json",
            data=json.dumps(intelligence_data)
        )
        logger.info(f"Added intelligence to Zep graph for {conversation_id}")
        
    except Exception as e:
        logger.debug(f"Could not add to graph: {e}")


async def get_zep_context(conversation_id: str) -> str:
    """
    Get Zep context block for a conversation.
    Returns optimized context string for LLM prompts.
    
    Args:
        conversation_id: Thread ID
        
    Returns:
        Context block string
    """
    client = _get_zep_client()
    if not client:
        return ""
    
    try:
        user_context = client.thread.get_user_context(thread_id=conversation_id)
        if user_context and hasattr(user_context, 'context'):
            return user_context.context or ""
    except Exception as e:
        logger.debug(f"Could not get Zep context: {e}")
    
    return ""


async def search_similar_scams(message: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search for similar scam patterns from Zep graph.
    
    Args:
        message: Message to search for similar patterns
        limit: Maximum number of results
        
    Returns:
        List of similar scam contexts
    """
    client = _get_zep_client()
    if not client:
        return []
    
    try:
        results = client.graph.search(
            user_id=HONEYPOT_USER_ID,
            query=message,
            limit=limit
        )
        
        similar_contexts = []
        if results:
            for result in results:
                similar_contexts.append({
                    "content": result.content if hasattr(result, 'content') else str(result),
                    "score": result.score if hasattr(result, 'score') else 0.0
                })
        
        return similar_contexts
        
    except Exception as e:
        logger.debug(f"Graph search not available: {e}")
        return []


def inject_memory_into_state(state: Dict[str, Any], memory: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inject loaded memory context into LangGraph state.
    
    Args:
        state: Current LangGraph state
        memory: Loaded memory context from Zep
        
    Returns:
        Enhanced state with memory context
    """
    if not memory:
        return state
    
    enhanced_state = dict(state)
    
    # Inject Zep context for improved LLM prompts
    enhanced_state["zep_context"] = memory.get("zep_context", "")
    enhanced_state["prior_context"] = memory.get("conversation_summary", "")
    enhanced_state["prior_scam_types"] = memory.get("prior_scam_types", [])
    enhanced_state["behavioral_signals"] = memory.get("behavioral_signals", [])
    
    # Merge prior entities (avoid duplicates)
    prior_entities = memory.get("prior_entities", {})
    current_entities = enhanced_state.get("extracted_entities", {
        "bank_accounts": [],
        "upi_ids": [],
        "phishing_urls": []
    })
    
    for key in ["bank_accounts", "upi_ids", "phishing_urls"]:
        prior_list = prior_entities.get(key, [])
        current_list = current_entities.get(key, [])
        merged = list(set(prior_list + current_list))
        current_entities[key] = merged
    
    enhanced_state["extracted_entities"] = current_entities
    
    # Add prior messages for conversation continuity
    if memory.get("prior_messages"):
        enhanced_state["prior_messages"] = memory["prior_messages"][-10:]
    
    return enhanced_state


def is_zep_available() -> bool:
    """Check if Zep is configured and available."""
    return _get_zep_client() is not None
