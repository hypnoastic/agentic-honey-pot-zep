import asyncio
import os
from memory.postgres_memory import _get_pool
from dotenv import load_dotenv

load_dotenv()

async def check_db():
    pool = await _get_pool()
    if not pool:
        print("Could not connect to database")
        return

    async with pool.acquire() as conn:
        print("--- LATEST SESSIONS ---")
        sessions = await conn.fetch("SELECT session_id, scam_type, metadata FROM sessions ORDER BY updated_at DESC LIMIT 3")
        for s in sessions:
            print(f"ID: {s['session_id']}, Type: {s['scam_type']}, Metadata: {s['metadata']}")
            
            print(f"  --- MESSAGES FOR {s['session_id']} ---")
            msgs = await conn.fetch("SELECT role, content FROM messages WHERE session_id = $1 ORDER BY created_at ASC", s['session_id'])
            for m in msgs:
                print(f"    [{m['role']}]: {m['content'][:50]}...")

if __name__ == "__main__":
    asyncio.run(check_db())
