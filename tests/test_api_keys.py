import os
import asyncio
from dotenv import load_dotenv
import openai
from google import genai
import logging
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API-Test")

load_dotenv()

async def test_openai():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("❌ OpenAI API Key not found in .env")
        return
    
    logger.info(f"Testing OpenAI Key (ending in ...{api_key[-5:]})")
    client = openai.AsyncOpenAI(api_key=api_key)
    try:
        response = await client.embeddings.create(
            input="test",
            model="text-embedding-3-small"
        )
        logger.info("✅ OpenAI Connection Successful (Embeddings)")
    except Exception as e:
        logger.error(f"❌ OpenAI Connection Failed: {e}")

async def test_gemini():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("❌ Gemini API Key not found in .env")
        return
    
    logger.info(f"Testing Gemini Key (ending in ...{api_key[-5:]})")
    client = genai.Client(api_key=api_key)
    try:
        # Simple generation test
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Say 'API Key Active'"
        )
        logger.info(f"✅ Gemini Connection Successful. Reply: {response.text.strip()}")
    except Exception as e:
        logger.error(f"❌ Gemini Connection Failed: {e}")

async def test_serper():
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        logger.error("❌ Serper API Key not found in .env")
        return
    
    logger.info(f"Testing Serper Key (ending in ...{api_key[-5:]})")
    url = "https://google.serper.dev/search"
    payload = {"q": "test search"}
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                logger.info("✅ Serper Connection Successful")
            else:
                logger.error(f"❌ Serper Connection Failed: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"❌ Serper Connection Failed: {e}")

async def main():
    logger.info("--- Starting API Diagnostic ---")
    await test_openai()
    print("-" * 20)
    await test_gemini()
    print("-" * 20)
    await test_serper()
    logger.info("--- Diagnostic Complete ---")

if __name__ == "__main__":
    asyncio.run(main())
