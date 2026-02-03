"""
Zep Context AI Memory Integration
Provides persistent conversational memory and intelligence context for the honeypot system.
Uses Zep Cloud SDK with User, Thread, and Graph APIs per official documentation.
"""

import json
import logging
import uuid
from typing import Dict, Any, List, Optional, Union
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
                # Added explicit verification log for user
                logger.info(f"[ZEP VERIFICATION] Successfully retrieved context for thread {conversation_id}")
                if memory_context["zep_context"]:
                    logger.info(f"[ZEP DATA] Context Preview: {memory_context['zep_context'][:100]}...")
                else:
                    logger.info("[ZEP DATA] No explicit context found yet (fresh conversation).")
        except Exception as e:
            logger.debug(f"No user context available: {e}")
        
        # Get thread messages for prior conversation history
        try:
             # Use RAW API since SDK seems to lack list method or is inconsistent
             import httpx
             url = f"https://api.getzep.com/api/v2/threads/{conversation_id}/messages?limit=100"
             headers = {
                 "Authorization": f"Api-Key {settings.zep_api_key}",
                 "Content-Type": "application/json"
             }
             
             async with httpx.AsyncClient() as http_client:
                 response = await http_client.get(url, headers=headers)
                 if response.status_code == 200:
                     response_data = response.json()
                     # It might be a list or object with 'messages'
                     raw_messages = response_data.get('messages', []) if isinstance(response_data, dict) else response_data
                     
                     if raw_messages:
                         for msg in raw_messages:
                             # Handle dict format from raw JSON
                             role = msg.get("role", "user")
                             content = msg.get("content", "")
                             name = msg.get("name")
                             created_at = msg.get("created_at")
                             
                             memory_context["prior_messages"].append({
                                 "role": role,
                                 "content": content,
                                 "name": name,
                                 "timestamp": created_at
                             })
                         logger.info(f"Loaded {len(memory_context['prior_messages'])} messages via Raw API")
                 else:
                     logger.debug(f"Failed to list messages via Raw API: {response.status_code}")

        except Exception as e:
            logger.debug(f"Error fetching messages: {e}")
        
        # SCAN MESSAGES FOR PERSISTED PERSONA (Fallback)
        # We look for the MOST RECENT system message with our marker
        if memory_context["prior_messages"]:
            for msg in reversed(memory_context["prior_messages"]):
                content = msg.get("content", "")
                if content.startswith("__PERSONA_METADATA__"):
                    try:
                        json_str = content.replace("__PERSONA_METADATA__", "")
                        data = json.loads(json_str)
                        memory_context["persona_name"] = data.get("name")
                        memory_context["persona_context"] = data.get("context")
                        # Also merge entities if useful
                        logger.info(f"[ZEP PERSONA] Restored persona from System Message: {data.get('name')}")
                        break
                    except Exception as e:
                        logger.warning(f"Failed to parse persona marker: {e}")

        if memory_context["prior_messages"]:
            # Filter out the persona marker messages so they don't confuse the LLM context
            memory_context["prior_messages"] = [
                m for m in memory_context["prior_messages"] 
                if not m.get("content", "").startswith("__PERSONA_METADATA__")
            ]
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
        

        # PERSIST PERSONA AS SYSTEM MESSAGE (Fallback technique)
        # Since metadata updates are restricted/unavailable in this SDK version
        if state.get("persona_name"):
             try:
                 persona_data = {
                     "name": state.get("persona_name"),
                     "context": state.get("persona_context"),
                     "traits": state.get("persona_traits", {}),
                     "entities": state.get("extracted_entities", {})
                 }
                 marker = f"__PERSONA_METADATA__{json.dumps(persona_data)}"
                 
                 # Check if we already added it recently to avoid duplication?
                 # Actually, it's fine to add it at the end of a batch.
                 # Zep will index it.
                 
                 system_msg = Message(
                     created_at=datetime.now(timezone.utc).isoformat(),
                     role="system", 
                     name="System",
                     content=marker
                 )
                 
                 client.thread.add_messages(
                     thread_id=conversation_id,
                     messages=[system_msg]
                 )
                 logger.info(f"Persisted Persona '{state.get('persona_name')}' as System Message.")
             except Exception as e:
                 logger.warning(f"Failed to save persona system message: {e}")

        # Add extracted intelligence to graph as business data
        if is_final and state.get("scam_detected"):
            await _add_intelligence_to_graph(client, conversation_id, state)
        
        return True

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
            "persona_traits": state.get("persona_traits", {}),
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


async def search_winning_strategies(scam_type: str, limit: int = 3) -> List[str]:
    """
    Search Zep graph for past successful extractions for this scam type.
    Returns a list of strategies/insights.
    """
    client = _get_zep_client()
    if not client or not scam_type:
        return []
        
    try:
        # We search for the specific scam type combined with "scam_detected"
        # This targets the JSON nodes we persisted in _add_intelligence_to_graph
        query = f"{scam_type} scam_detected"
        
        results = client.graph.search(
            user_id=HONEYPOT_USER_ID,
            query=query,
            limit=limit * 2 # Fetch more to filter
        )
        
        strategies = []
        if results:
            for result in results:
                try:
                    # The content is a JSON string of the intelligence event
                    content = result.content if hasattr(result, 'content') else str(result)
                    if "bank_accounts" in content or "upi_ids" in content:
                        data = json.loads(content)
                        # Only use if we actually extracted something
                        has_extraction = (
                            len(data.get("bank_accounts", [])) > 0 or 
                            len(data.get("upi_ids", [])) > 0 or
                            len(data.get("phishing_urls", [])) > 0
                        )
                        
                        if has_extraction:
                            persona = data.get("persona_used", "Unknown")
                            turns = data.get("engagement_turns", 0)
                            strategies.append(f"Used persona '{persona}' to extract entities in {turns} turns.")
                except:
                    continue
                    
        return list(set(strategies))[:limit]
        
    except Exception as e:
        logger.debug(f"Strategy search failed: {e}")
        return []


async def add_failure_event(conversation_id: str, state: Dict[str, Any]):
    """
    Log a failed engagement to Zep graph (Anti-Pattern Learning).
    Triggered when max turns reached with NO extractions.
    """
    client = _get_zep_client()
    if not client:
        return

    try:
        failure_data = {
            "event_type": "engagement_failure",
            "conversation_id": conversation_id,
            "scam_type": state.get("scam_type"),
            "reason": "max_turns_reached_no_extraction", # Standardize failure reasons
            "persona_used": state.get("persona_name"),
            "strategy_hint": state.get("strategy_hint"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        client.graph.add(
            user_id=HONEYPOT_USER_ID,
            type="json",
            data=json.dumps(failure_data)
        )
        logger.info(f"Logged FAILURE event for {conversation_id}")
        
    except Exception as e:
        logger.debug(f"Could not log failure: {e}")


async def search_past_failures(scam_type: str, limit: int = 3) -> List[str]:
    """
    Search Zep graph for past failures to avoid repeating mistakes.
    """
    client = _get_zep_client()
    if not client or not scam_type:
        return []
        
    try:
        query = f"{scam_type} engagement_failure"
        results = client.graph.search(
            user_id=HONEYPOT_USER_ID,
            query=query,
            limit=limit * 2
        )
        
        failures = []
        if results:
            for result in results:
                try:
                    content = result.content if hasattr(result, 'content') else str(result)
                    if "engagement_failure" in content:
                        data = json.loads(content)
                        persona = data.get("persona_used", "Unknown")
                        failures.append(f"Persona '{persona}' failed to extract info.")
                except:
                    continue
                    
        return list(set(failures))[:limit]
        
    except Exception as e:
        logger.debug(f"Failure search failed: {e}")
        return []


async def get_scam_stats(scam_type: str) -> Dict[str, Union[int, float]]:
    """
    Retrieve success/failure statistics for a scam type from Zep graph.
    Used for ROI Logic (Strategic Pruning).
    """
    client = _get_zep_client()
    if not client or not scam_type:
        return {"success_rate": 0.5, "total_attempts": 0} # Default neutral
        
    try:
        # Search for both success and failure nodes
        # This is a simplified "search-count" approach. 
        # Ideally, Zep graph traversal would aggregate this, but search is easier for now.
        
        success_query = f"{scam_type} scam_detected" # We use this pattern for successful extractions
        failure_query = f"{scam_type} engagement_failure"
        
        # We need counts, not content. 
        # Limitation: Zep Search limit is finite. We can't get true global counts easily without traversal.
        # Approximation: Retrieve top 20 of each and estimate density?
        # Better: Just assume we have "some" memory.
        
        success_results = client.graph.search(user_id=HONEYPOT_USER_ID, query=success_query, limit=50)
        failure_results = client.graph.search(user_id=HONEYPOT_USER_ID, query=failure_query, limit=50)
        
        success_count = 0
        if success_results:
            # Filter strictly
            for res in success_results:
                content = res.content if hasattr(res, 'content') else str(res)
                if "scam_detected" in content and ("bank_accounts" in content or "upi_ids" in content):
                    success_count += 1
        
        failure_count = 0
        if failure_results:
            for res in failure_results:
                content = res.content if hasattr(res, 'content') else str(res)
                if "engagement_failure" in content:
                    failure_count += 1
                    
        total = success_count + failure_count
        if total == 0:
             return {"success_rate": 0.5, "total_attempts": 0}
             
        rate = success_count / total
        return {"success_rate": rate, "total_attempts": total}

    except Exception as e:
        logger.debug(f"Stats retrieval failed: {e}")
        return {"success_rate": 0.5, "total_attempts": 0}


async def get_scam_signal(message: str) -> Dict[str, Any]:
    """
    Get valid, lightweight Zep signal for the detection agent.
    Returns: { "similar_count": 5, "common_type": "UPI_FRAUD" }
    """
    client = _get_zep_client()
    if not client:
        return {"similar_count": 0, "common_type": None}
        
    try:
        # Fast search for similar messages
        results = client.graph.search(
            user_id=HONEYPOT_USER_ID,
            query=message,
            limit=10
        )
        
        if not results:
             return {"similar_count": 0, "common_type": None}
             
        # Aggregate stats
        types = []
        count = 0
        for res in results:
            content = res.content if hasattr(res, 'content') else str(res)
            # Check if this node is a stored stats node or failure node
            if "scam_detected" in content or "engagement_failure" in content:
                count += 1
                # Try to extract type if possible
                if "UPI_FRAUD" in content: types.append("UPI_FRAUD")
                elif "BANK_IMPERSONATION" in content: types.append("BANK_IMPERSONATION")
                elif "PHISHING" in content: types.append("PHISHING")
                elif "LOTTERY_FRAUD" in content: types.append("LOTTERY_FRAUD")
                elif "INVESTMENT_SCAM" in content: types.append("INVESTMENT_SCAM")
                
        common_type = max(set(types), key=types.count) if types else "Unknown"
        
        return {
            "similar_count": count,
            "common_type": common_type
        }

    except Exception as e:
        logger.debug(f"Signal retrieval failed: {e}")
        return {"similar_count": 0, "common_type": None}


async def get_optimal_traits(scam_type: str) -> Dict[str, Any]:
    """
    Search Zep graph for winning persona trait vectors for this scam type.
    Returns aggregated optimal traits (e.g., {"tech_literacy": "low", "age": "60+"})
    """
    client = _get_zep_client()
    if not client or not scam_type:
        return {}
        
    try:
        # Search for success nodes
        query = f"{scam_type} scam_detected"
        results = client.graph.search(
            user_id=HONEYPOT_USER_ID,
            query=query,
            limit=10
        )
        
        if not results:
            return {}
            
        # Collect traits from successful nodes
        all_traits = []
        for res in results:
            content = res.content if hasattr(res, 'content') else str(res)
            try:
                # Check for extraction
                if "bank_accounts" in content or "upi_ids" in content:
                    data = json.loads(content)
                    traits = data.get("persona_traits", {})
                    if traits:
                        all_traits.append(traits)
            except:
                continue
                
        # Simple aggregation: Return the most recent winning traits (first result usually)
        # OR better: if we have multiple, return the most frequent values?
        # For now, let's grab the MOST RELEVANT one (top search result with traits)
        if all_traits:
            return all_traits[0]
            
        return {}

    except Exception as e:
        logger.debug(f"Optimal traits search failed: {e}")
        return {}


async def get_temporal_stats(scam_type: str) -> Dict[str, Union[float, int]]:
    """
    Retrieve temporal statistics (avg turns to extraction) for a scam type.
    Used for pacing the engagement.
    """
    client = _get_zep_client()
    if not client or not scam_type:
        return {"avg_turns": 4.0, "sample_size": 0} # Default assumption
        
    try:
        query = f"{scam_type} scam_detected"
        results = client.graph.search(
            user_id=HONEYPOT_USER_ID,
            query=query,
            limit=20
        )
        
        if not results:
             return {"avg_turns": 4.0, "sample_size": 0}
             
        turns_list = []
        for res in results:
            content = res.content if hasattr(res, 'content') else str(res)
            try:
                if "engagement_turns" in content:
                    data = json.loads(content)
                    turns = data.get("engagement_turns", 0)
                    if turns > 0:
                        turns_list.append(turns)
            except:
                continue
                
        if not turns_list:
             return {"avg_turns": 4.0, "sample_size": 0}
             
        avg = sum(turns_list) / len(turns_list)
        return {"avg_turns": round(avg, 1), "sample_size": len(turns_list)}

    except Exception as e:
        logger.debug(f"Temporal stats failed: {e}")
        return {"avg_turns": 4.0, "sample_size": 0}


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
        
    # INJECT RESTORED PERSONA INTO STATE
    if memory.get("persona_name"):
        enhanced_state["persona_name"] = memory["persona_name"]
        enhanced_state["persona_context"] = memory.get("persona_context", "")

    return enhanced_state


def is_zep_available() -> bool:
    """Check if Zep is configured and available."""
    return _get_zep_client() is not None
