"""
Database Initialization Script for Agentic Honey-Pot (Neon + pgvector).
Run this script to set up the database schema.
Env variable DATABASE_URL must be set.
"""

import asyncio
import os
import asyncpg
import logging
from dotenv import load_dotenv

# Load env vars
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

async def init_db():
    if not DATABASE_URL:
        logger.error("DATABASE_URL environment variable not set!")
        return

    logger.info(f"Connecting to database...")
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        logger.info("Creating extension vector...")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

        logger.info("Creating tables...")
        
        # 1. Sessions Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id UUID PRIMARY KEY,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                scam_type TEXT,
                status TEXT DEFAULT 'active',
                metadata JSONB DEFAULT '{}'::JSONB
            );
        """)
        
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_scam_type ON sessions(scam_type);")

        # 2. Messages Table
        # Using 1536 dims for text-embedding-3-small
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id UUID REFERENCES sessions(session_id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding vector(1536)
            );
        """)
        
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_embedding ON messages USING hnsw (embedding vector_cosine_ops);")

        # 3. Intelligence Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS intelligence (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id UUID REFERENCES sessions(session_id),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                event_type TEXT NOT NULL,
                scam_type TEXT,
                summary TEXT NOT NULL,
                payload JSONB DEFAULT '{}'::JSONB,
                embedding vector(1536)
            );
        """)

        # Optimized HNSW index with tuned parameters
        await conn.execute("""CREATE INDEX IF NOT EXISTS idx_intelligence_embedding 
            ON intelligence USING hnsw (embedding vector_cosine_ops) 
            WITH (m = 24, ef_construction = 128);""")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_intelligence_type ON intelligence(event_type, scam_type);")
        # Composite index for common queries
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_intelligence_composite ON intelligence(event_type, scam_type, created_at DESC);")
        
        logger.info("Database initialization complete.")
        await conn.close()
        
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        # Hint for asyncpg ssl error
        if "ssl" in str(e).lower():
            logger.info("Try adding ?sslmode=require to your DATABASE_URL")

if __name__ == "__main__":
    asyncio.run(init_db())
