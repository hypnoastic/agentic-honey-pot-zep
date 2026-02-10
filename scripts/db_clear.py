
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

async def clear_db():
    if not DATABASE_URL:
        logger.error("DATABASE_URL environment variable not set!")
        return

    logger.info(f"Connecting to database to CLEAR all data...")
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        logger.info("Truncating tables...")
        
        # Truncate tables with CASCADE to handle foreign keys
        await conn.execute("TRUNCATE TABLE messages, intelligence, sessions CASCADE;")
        
        logger.info("Database cleared successfully.")
        await conn.close()
        
    except Exception as e:
        logger.error(f"Clear failed: {e}")

if __name__ == "__main__":
    asyncio.run(clear_db())
