
import asyncio
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.llm_client import call_llm_async
from config import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_model():
    settings = get_settings()
    logger.info(f"Testing connectivity with Planner Model: {settings.planner_model}")
    
    try:
        response = await call_llm_async(
            prompt="Hello, return 'OK' if you can read this.",
            system_instruction="You are a test bot.",
            agent_name="planner"
        )
        logger.info(f"✅ Model Response: {response}")
    except Exception as e:
        logger.error(f"❌ connectivity failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_model())
