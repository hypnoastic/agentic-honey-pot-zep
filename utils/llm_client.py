import logging
import time
import asyncio
import threading
from typing import Optional, List, Dict, Union
import openai
from openai import OpenAI, AsyncOpenAI, APIError, RateLimitError, APITimeoutError
from google import genai
from google.genai import types
from config import get_settings, get_model_for_agent

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMClient:
    """Singleton LLM client with thread-safe initialization."""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super(LLMClient, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        # OpenAI (for Embeddings)
        self.openai_api_key = settings.openai_api_key
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not found in settings! Embeddings will fail.")
        
        self.openai_client = OpenAI(api_key=self.openai_api_key, timeout=settings.openai_timeout)
        self.openai_async_client = AsyncOpenAI(api_key=self.openai_api_key, timeout=settings.openai_timeout)
        
        # Gemini (for Agents)
        self.gemini_api_key = settings.gemini_api_key
        if not self.gemini_api_key:
            logger.error("GEMINI_API_KEY not found in settings! Agents will fail.")
            raise ValueError("GEMINI_API_KEY is required for agent migration.")
            
        self.gemini_client = genai.Client(api_key=self.gemini_api_key)
        
        self._initialized = True
        logger.info(f"LLMClient initialized. Agents use Gemini, Embeddings use OpenAI.")

    def generate_response(
        self, 
        prompt: str, 
        system_instruction: Optional[str] = None, 
        json_mode: bool = False,
        model: Optional[str] = None,
        agent_name: Optional[str] = None,
        temperature: float = 0.0
    ) -> str:
        """
        Generate a response from Gemini with retry logic.
        """
        # Determine model to use
        if model:
            use_model = model
        elif agent_name:
            use_model = get_model_for_agent(agent_name)
        else:
            use_model = settings.planner_model or "gemini-2.0-flash"
            
        if use_model.lower().startswith("gpt"):
            logger.warning(f"⚠️ WARNING: Agent '{agent_name}' is attempting to use GPT model: {use_model}")

        settings_local = get_settings()
        retries = settings_local.api_retry_attempts
        last_error = None

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            response_mime_type="application/json" if json_mode else "text/plain"
        )

        for attempt in range(retries):
            try:
                response = self.gemini_client.models.generate_content(
                    model=use_model,
                    contents=prompt,
                    config=config
                )
                return response.text
                
            except Exception as e:
                last_error = e
                wait_time = 2 ** attempt
                logger.warning(f"Gemini API Error (Attempt {attempt+1}/{retries}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
        
        logger.error(f"Failed to generate Gemini response after {retries} attempts. Last error: {last_error}")
        raise last_error or Exception("Unknown error in Gemini generation")

    async def generate_response_async(
        self, 
        prompt: str, 
        system_instruction: Optional[str] = None, 
        json_mode: bool = False,
        model: Optional[str] = None,
        agent_name: Optional[str] = None,
        temperature: float = 0.0
    ) -> str:
        """
        Generate a response from Gemini ASYNC with retry logic.
        """
        # Determine model to use
        if model:
            use_model = model
        elif agent_name:
            use_model = get_model_for_agent(agent_name)
        else:
            use_model = settings.planner_model or "gemini-2.0-flash"
            
        if use_model.lower().startswith("gpt"):
            logger.warning(f"⚠️ WARNING: Agent '{agent_name}' is attempting to use GPT model: {use_model}")

        settings_local = get_settings()
        retries = settings_local.api_retry_attempts
        last_error = None

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            response_mime_type="application/json" if json_mode else "text/plain"
        )

        for attempt in range(retries):
            try:
                # google-genai SDK 1.x generate_content is synchronous but can be wrapped or used if there's an async counterpart.
                # Currently, google-genai Client.models.generate_content is synchronous.
                # If we need true async, we might need a different approach, but for now we wrap it.
                response = await asyncio.to_thread(
                    self.gemini_client.models.generate_content,
                    model=use_model,
                    contents=prompt,
                    config=config
                )
                return response.text
                
            except Exception as e:
                last_error = e
                wait_time = 2 ** attempt
                logger.warning(f"Async Gemini API Error (Attempt {attempt+1}/{retries}): {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
        
        logger.error(f"Failed to generate async Gemini response after {retries} attempts. Last error: {last_error}")
        raise last_error or Exception("Unknown error in Gemini generation")

    async def get_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI (STRICT)."""
        if not text:
            return []
            
        model = settings.embedding_model
        try:
            response = await self.openai_async_client.embeddings.create(
                input=text.replace("\n", " "),
                model=model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise e

    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts using OpenAI (STRICT).
        """
        if not texts:
            return []
            
        model = settings.embedding_model
        try:
            clean_texts = [t.replace("\n", " ") for t in texts]
            response = await self.openai_async_client.embeddings.create(
                input=clean_texts,
                model=model
            )
            return [data.embedding for data in response.data]
            
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            raise e


# Global instance
_client_instance = None


def get_llm_client() -> LLMClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = LLMClient()
    return _client_instance


def call_llm(
    prompt: str, 
    system_instruction: Optional[str] = None, 
    json_mode: bool = False,
    agent_name: Optional[str] = None,
    temperature: float = 0.0
) -> str:
    """
    Helper function to call the singleton client (Gemini for agents).
    
    Args:
        prompt: User prompt
        system_instruction: System instruction
        json_mode: Whether to force JSON response
        agent_name: Agent name for automatic model selection
    """
    client = get_llm_client()
    return client.generate_response(
        prompt=prompt, 
        system_instruction=system_instruction, 
        json_mode=json_mode,
        agent_name=agent_name,
        temperature=temperature
    )


async def call_llm_async(
    prompt: str, 
    system_instruction: Optional[str] = None, 
    json_mode: bool = False,
    agent_name: Optional[str] = None,
    temperature: float = 0.0
) -> str:
    """Helper function for async Gemini calls."""
    client = get_llm_client()
    return await client.generate_response_async(
        prompt=prompt, 
        system_instruction=system_instruction, 
        json_mode=json_mode,
        agent_name=agent_name,
        temperature=temperature
    )


async def get_embedding(text: str) -> List[float]:
    """Helper to get OpenAI embeddings."""
    client = get_llm_client()
    return await client.get_embedding(text)


async def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Helper to get batch OpenAI embeddings."""
    client = get_llm_client()
    return await client.get_embeddings_batch(texts)
