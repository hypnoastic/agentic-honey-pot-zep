"""
Neon PostgreSQL Memory Integration
Provides persistent conversational memory and intelligence context using pgvector.
"""

import json
import logging
import uuid
import asyncio
import asyncpg
import numpy as np
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone

from config import get_settings
from utils.llm_client import get_embedding
from pgvector.asyncpg import register_vector

settings = get_settings()
logger = logging.getLogger(__name__)

# Connection pool singleton
_pool = None

async def _init_connection(conn):
    """Initialize connection with vector support and HNSW tuning."""
    await register_vector(conn)
    # Tune HNSW search for better recall/performance balance
    await conn.execute("SET hnsw.ef_search = 100;")

async def _get_pool():
    """Get or create PostgreSQL connection pool. Loop-safe for tests."""
    global _pool
    current_loop = asyncio.get_running_loop()
    
    # If pool exists, check if it's tied to a different loop
    if _pool is not None:
        try:
            # Internal check for asyncpg pool loop
            if getattr(_pool, "_loop", None) != current_loop:
                logger.warning("PostgreSQL pool mismatch: loop has changed. Recreating pool.")
                # Attempt to close old pool if possible, but don't block
                # Calling close() might fail if the old loop is already closed/dead
                _pool = None
        except Exception:
            _pool = None

    if _pool is None and settings.database_url:
        try:
            _pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=3,  # Increased from 1 for better concurrency
                max_size=10,
                timeout=30,
                command_timeout=60,
                server_settings={'application_name': 'honeypot'},
                init=_init_connection
            )
            logger.info("PostgreSQL connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL pool: {e}")
            _pool = None
    return _pool

async def init_db_pool():
    """Explicitly initialize the pool (useful for startup)."""
    await _get_pool()

async def load_conversation_memory(conversation_id: str, conn: Optional[asyncpg.Connection] = None) -> Dict[str, Any]:
    """
    Load prior conversation context from PostgreSQL.
    Directly queries the database for session metadata and messages.
    """
    if conn:
        return await _load_memory_impl(conn, conversation_id)

    pool = await _get_pool()
    if not pool:
        return {}
        
    async with pool.acquire() as conn:
        return await _load_memory_impl(conn, conversation_id)

async def _load_memory_impl(conn: asyncpg.Connection, conversation_id: str) -> Dict[str, Any]:
    memory_context = {
        "prior_messages": [],
        "prior_entities": {
            "bank_accounts": [],
            "upi_ids": [],
            "phishing_urls": []
        },
        "prior_scam_types": [],
        "behavioral_signals": [],
        "conversation_summary": ""
    }
    
    try:
        # 1. Fetch Session Metadata (Persona, etc.)
        row = await conn.fetchrow(
            "SELECT metadata FROM sessions WHERE session_id = $1",
            conversation_id
        )
                
        if row and row['metadata']:
            meta = row['metadata']
            if isinstance(meta, str):
                meta = json.loads(meta)
            
            memory_context["conversation_summary"] = meta.get("summary", "")
            memory_context["persona_name"] = meta.get("persona_name")
            # Ensure persona_context is a string for json.loads in agent
            p_ctx = meta.get("persona_context")
            if isinstance(p_ctx, dict):
                memory_context["persona_context"] = json.dumps(p_ctx)
            else:
                memory_context["persona_context"] = p_ctx or "{}"
                
            memory_context["persona_traits"] = meta.get("persona_traits", {})
            memory_context["engagement_count"] = meta.get("engagement_count", 0)
            memory_context["engagement_complete"] = meta.get("engagement_complete", False)
            memory_context["scam_detected"] = meta.get("scam_detected", False)
            memory_context["extraction_complete"] = meta.get("extraction_complete", False)
            
            # Restore entities
            if "extracted_entities" in meta:
                extracted = meta["extracted_entities"]
                for k in ["bank_accounts", "upi_ids", "phishing_urls", "phone_numbers", "ifsc_codes"]:
                    if k in extracted and isinstance(extracted[k], list):
                        current = memory_context["prior_entities"].get(k, [])
                        for item in extracted[k]:
                            if item not in current:
                                current.append(item)
                        memory_context["prior_entities"][k] = current

        # 2. Fetch Recent Messages (Last 20)
        rows = await conn.fetch(
            """
            SELECT role, content, 'name' as name, created_at 
            FROM messages 
            WHERE session_id = $1 
            ORDER BY created_at DESC 
            LIMIT 20
            """,
            conversation_id
        )
                
        # Reverse to get chronological order
        for r in reversed(rows):
            memory_context["prior_messages"].append({
                "role": r["role"],
                "content": r["content"],
                "timestamp": r["created_at"].isoformat() if r["created_at"] else None
            })
        
        logger.info(f"Loaded {len(memory_context['prior_messages'])} messages from Postgres")

    except Exception as e:
        logger.error(f"Error loading memory for {conversation_id}: {e}")

    return memory_context

async def persist_conversation_memory(
    conversation_id: str,
    state: Dict[str, Any],
    is_final: bool = False,
    conn: Optional[asyncpg.Connection] = None,
    background_embedding: bool = False
) -> bool:
    """
    Persist conversation turns and extracted intelligence to Postgres.
    Args:
        background_embedding: If True, skip intelligence embedding for faster response (200-300ms savings)
    """
    if conn:
        return await _persist_memory_impl(conn, conversation_id, state, is_final, background_embedding)

    pool = await _get_pool()
    if not pool:
        return False

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                return await _persist_memory_impl(conn, conversation_id, state, is_final, background_embedding)
    except Exception as e:
        logger.error(f"Error persisting (PostgresWrapper): {e}")
        return False


async def _persist_memory_impl(conn: asyncpg.Connection, conversation_id: str, state: Dict[str, Any], is_final: bool, background_embedding: bool = False) -> bool:
    try:
        # 1. Upsert Session
        # We need to make sure session exists.
        # If it doesn't, create it. If it does, update metadata.
        
        metadata = {
            "persona_name": state.get("persona_name"),
            "persona_context": state.get("persona_context"),
            "persona_traits": state.get("persona_traits", {}),
            "extracted_entities": state.get("extracted_entities", {}),
            "scam_type": state.get("scam_type"),
            "summary": state.get("conversation_summary", ""),
            "engagement_count": state.get("engagement_count", 0),
            "engagement_complete": state.get("engagement_complete", False),
            "scam_detected": state.get("scam_detected", False),
            "extraction_complete": state.get("extraction_complete", False)
        }
        
        # VERIFICATION LOGGING FOR USER
        # Removed print statements for security (no metadata leakage)
        
        await conn.execute(
            """
            INSERT INTO sessions (session_id, scam_type, metadata, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (session_id) 
            DO UPDATE SET 
                metadata = sessions.metadata || EXCLUDED.metadata,
                scam_type = COALESCE(EXCLUDED.scam_type, sessions.scam_type),
                updated_at = NOW()
            """,
            conversation_id,
            state.get("scam_type"),
            json.dumps(metadata)
        )

        # 2. Insert Messages (Optimized with Batch Embeddings)
        await conn.execute("DELETE FROM messages WHERE session_id = $1", conversation_id)
        
        # Collect all texts to embed
        history = state.get("conversation_history", [])
        original_msg = state.get("original_message", "")
        
        texts_to_embed = []
        if original_msg:
            texts_to_embed.append(original_msg)
            
        # 2. Batch Insert Messages with Embedding Tracking
        # Only embed user/scammer messages for search relevance
        # Track which messages need embeddings vs already have them
        embed_map = {} 
        texts_to_embed = []
        
        for i, turn in enumerate(history):
            role = "assistant" if turn.get("role") == "honeypot" else "user"
            content = turn.get("message", "")
            # Only embed user messages that don't already have embeddings
            if role == "user" and content and not turn.get("embedding"):
                embed_map[i] = len(texts_to_embed)
                texts_to_embed.append(content)
        
        # Add original message if not already embedded
        if original_msg and not state.get("original_message_embedding"):
            texts_to_embed.insert(0, original_msg)
                
        # Generate all embeddings in ONE call
        from utils.llm_client import get_embeddings_batch
        embeddings = []
        if texts_to_embed:
            try:
                embeddings = await get_embeddings_batch(texts_to_embed)
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                # Fallback: empty list, will result in None embeddings
        
        # Batch insert all messages (180ms savings)
        batch_inserts = []
        
        # Add original message
        if original_msg:
            emb = embeddings[0] if embeddings else None
            batch_inserts.append((conversation_id, 'user', original_msg, emb))
        
        # Add history messages
        for i, turn in enumerate(history):
            role = "assistant" if turn.get("role") == "honeypot" else "user"
            content = turn.get("message", "")
            
            emb = None
            if i in embed_map and embeddings and len(embeddings) > embed_map[i]:
                emb = embeddings[embed_map[i]]
            
            batch_inserts.append((conversation_id, role, content, emb))
        
        # Execute batch insert
        if batch_inserts:
            await conn.executemany(
                """INSERT INTO messages (session_id, role, content, embedding)
                   VALUES ($1, $2, $3, $4)""",
                batch_inserts
            )
        
        logger.info(f"Persisted {len(batch_inserts)} messages to Postgres (Batch Insert)")

        # 3. Add Intelligence Event (if final & detected)
        # Skip embedding if background_embedding=True for faster response (200-300ms savings)
        if is_final and state.get("scam_detected") and not background_embedding:
            await _add_intelligence_event(conn, conversation_id, state)
    
        return True

    except Exception as e:
        logger.error(f"Error persisting (Postgres): {e}")
        return False

async def _add_intelligence_event(conn, session_id, state):
    """Add scam detection event to intelligence table."""
    summary = f"Detected {state.get('scam_type')} using persona {state.get('persona_name')}."
    payload = {
        "event_type": "scam_detected",
        "scam_type": state.get("scam_type"),
        "confidence": state.get("confidence_score"),
        "entities": state.get("extracted_entities"),
        "persona_traits": state.get("persona_traits"),
        "turns": state.get("engagement_count")
    }
    
    # Embed the summary + scam type + entities for retrieval
    # "UPI Fraud. Extracted vpa@oksbi. Persona: Old Lady."
    text_to_embed = f"{state.get('scam_type')} {summary} {json.dumps(state.get('extracted_entities'))}"
    emb = await _get_embedding_safe(text_to_embed)
    
    await conn.execute(
        """
        INSERT INTO intelligence (session_id, event_type, scam_type, summary, payload, embedding)
        VALUES ($1, 'scam_detected', $2, $3, $4, $5)
        """,
        session_id, state.get("scam_type"), summary, json.dumps(payload), emb
    )
    logger.info(f"Added intelligence event for {session_id}")

async def add_failure_event(conversation_id: str, state: Dict[str, Any]):
    """Log failure event."""
    pool = await _get_pool()
    if not pool: return

    try:
        async with pool.acquire() as conn:
            summary = f"Failed to extract info. Scam: {state.get('scam_type')}. Persona: {state.get('persona_name')}."
            payload = {
                "event_type": "engagement_failure",
                "scam_type": state.get("scam_type"),
                "reason": "max_turns_reached",
                "persona": state.get("persona_name")
            }
            emb = await _get_embedding_safe(summary)
            
            await conn.execute(
                """
                INSERT INTO intelligence (session_id, event_type, scam_type, summary, payload, embedding)
                VALUES ($1, 'engagement_failure', $2, $3, $4, $5)
                """,
                conversation_id, state.get("scam_type"), summary, json.dumps(payload), emb
            )
    except Exception as e:
        logger.error(f"Failed to add failure event: {e}")

async def get_scam_signal(message: str) -> Dict[str, Any]:
    """Search for similar past scams."""
    pool = await _get_pool()
    if not pool: return {"similar_count": 0, "common_type": None}
    
    try:
        emb = await _get_embedding_safe(message)
        if not emb: return {"similar_count": 0, "common_type": None}
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT scam_type 
                FROM intelligence 
                WHERE event_type = 'scam_detected'
                ORDER BY embedding <=> $1 ASC
                LIMIT 10
                """,
                emb
            )
            
            if not rows: return {"similar_count": 0, "common_type": None}
            
            types = [r['scam_type'] for r in rows if r['scam_type']]
            if not types: return {"similar_count": 0, "common_type": None}
            
            common_type = max(set(types), key=types.count)
            return {
                "similar_count": len(rows),
                "common_type": common_type
            }
    except Exception as e:
        logger.error(f"Signal search failed: {e}")
        return {"similar_count": 0, "common_type": None}

async def search_winning_strategies(scam_type: str, limit: int = 3) -> List[str]:
    """Find winning strategies for a scam type."""
    pool = await _get_pool()
    if not pool: return []
    
    try:
        # We query for successful events of this type
        # Ideally we'd embed the query "winning strategy for {scam_type}" but simpler is filter by type
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT summary, payload 
                FROM intelligence 
                WHERE event_type = 'scam_detected' 
                  AND scam_type = $1
                ORDER BY created_at DESC 
                LIMIT $2
                """,
                scam_type, limit
            )
            
            strategies = []
            for r in rows:
                p = r['payload']
                if isinstance(p, str):
                    p = json.loads(p)
                
                persona = p.get('persona_traits', {}).get('age', 'unknown')
                turns = p.get('turns', 0)
                strategies.append(f"Used persona ({persona}) to extract in {turns} turns.")
            
            return strategies
    except Exception as e:
        logger.error(f"Strategy search failed: {e}")
        return []

async def search_past_failures(scam_type: str, limit: int = 3) -> List[str]:
    """Find past failures."""
    pool = await _get_pool()
    if not pool: return []
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT summary 
                FROM intelligence 
                WHERE event_type = 'engagement_failure' 
                  AND scam_type = $1
                ORDER BY created_at DESC 
                LIMIT $2
                """,
                scam_type, limit
            )
            return [r['summary'] for r in rows]
    except Exception as e:
        logger.error(f"Failure search failed: {e}")
        return []

async def get_scam_stats(scam_type: str) -> Dict[str, Union[int, float]]:
    """Get stats for scam type."""
    pool = await _get_pool()
    if not pool: return {"success_rate": 0.5, "total_attempts": 0}
    
    try:
        async with pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM intelligence WHERE scam_type = $1",
                scam_type
            )
            success = await conn.fetchval(
                "SELECT COUNT(*) FROM intelligence WHERE scam_type = $1 AND event_type = 'scam_detected'",
                scam_type
            )
            
            if total == 0: return {"success_rate": 0.5, "total_attempts": 0}
            return {"success_rate": success / total, "total_attempts": total}
            
    except Exception as e:
        logger.error(f"Stats failed: {e}")
        return {"success_rate": 0.5, "total_attempts": 0}

async def get_optimal_traits(scam_type: str) -> Dict[str, Any]:
    """Get optimal persona traits."""
    pool = await _get_pool()
    if not pool: return {}
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT payload 
                FROM intelligence 
                WHERE event_type = 'scam_detected' AND scam_type = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                scam_type
            )
            if row:
                p = row['payload']
                if isinstance(p, str):
                    p = json.loads(p)
                return p.get('persona_traits', {})
    except Exception:
        pass
    return {}

async def get_temporal_pacing(scam_type: str) -> Dict[str, Union[float, int]]:
    """Get pacing stats."""
    pool = await _get_pool()
    if not pool: return {"avg_turns": 4.0, "sample_size": 0}
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT payload 
                FROM intelligence 
                WHERE event_type = 'scam_detected' AND scam_type = $1
                LIMIT 20
                """,
                scam_type
            )
            
            turns = []
            for r in rows:
                p = r['payload']
                if isinstance(p, str):
                    p = json.loads(p)
                if 'turns' in p: turns.append(p['turns'])
            
            if not turns: return {"avg_turns": 4.0, "sample_size": 0}
            return {"avg_turns": sum(turns)/len(turns), "sample_size": len(turns)}
            
    except Exception:
        pass
    return {"avg_turns": 4.0, "sample_size": 0}

async def _get_embedding_safe(text: str) -> Optional[List[float]]:
    """Helper to get embedding with error handling."""
    try:
        # Use simple string for now, but in prod use LLM client
        from utils.llm_client import get_embedding
        return await get_embedding(text)
    except Exception as e:
        logger.warning(f"Embedding failed: {e}")
        # Return zero vector or None? None will fail DB insert if not nullable.
        # But we set embedding column nullable? No, we didn't specify NOT NULL.
        # But vector ops might fail.
        # Let's return a zero vector of size 1536 as fallback?
        # No, better to return None and handle logic.
        return None

def is_memory_available() -> bool:
    """Checks if PostgreSQL memory is enabled and configured."""
    return settings.postgres_enabled and bool(settings.database_url)

# Re-export search_similar_scams (alias for                        # Consolidate prior intelligence entities
async def search_similar_scams(message: str, limit: int = 5) -> List[Dict[str, Any]]:
    pool = await _get_pool()
    if not pool: return []
    try:
        emb = await _get_embedding_safe(message)
        if not emb: return []
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT summary, (embedding <=> $1) as dist 
                FROM intelligence 
                WHERE event_type = 'scam_detected'
                ORDER BY dist ASC
                LIMIT $2
                """,
                emb, limit
            )
            return [{"content": r['summary'], "score": 1 - r['dist']} for r in rows]
    except Exception:
        return []

from contextlib import asynccontextmanager

@asynccontextmanager
async def capture_session_lock(session_id: str):
    """
    Acquire a transactional lock for the session.
    Prevents race conditions by serializing requests for the same session_id.
    Yields the locked connection to be reused.
    """
    pool = await _get_pool()
    if not pool:
        yield None
        return

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Acquire row-level lock. If session doesn't exist, this does nothing (no lock).
            # But if it exists, it blocks others.
            # If it doesn't exist, we might race on INSERT.
            # To be safe, we use Advisory Lock based on session_id hash.
            
            # Use Advisory Lock (Transaction Level)
            # This works even if the row doesn't exist yet (first request).
            # hashtext returns 32-bit int.
            lock_key = await conn.fetchval("SELECT hashtext($1)", session_id)
            logger.info(f"[LOCK] Requesting lock for {session_id} (Key: {lock_key})")
            await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_key)
            logger.info(f"[LOCK] Acquired lock for {session_id}")
            
            try:
                yield conn
            finally:
                logger.info(f"[LOCK] Releasing lock for {session_id}")
