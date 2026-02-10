"""
LLM Client with per-agent model selection.
Supports GPT-5 family models: gpt-5, gpt-5-mini, gpt-5-nano
"""

import logging
import time
from typing import Optional, List, Dict, Union
import openai
from openai import OpenAI, APIError, RateLimitError, APITimeoutError
from config import get_settings, get_model_for_agent

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.api_key = settings.openai_api_key
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not found in settings!")
            
        self.client = OpenAI(api_key=self.api_key, timeout=settings.openai_timeout)
        self.default_model = settings.openai_model
        self._initialized = True
        logger.info(f"LLMClient initialized with default model: {self.default_model}")

    def generate_response(
        self, 
        prompt: str, 
        system_instruction: Optional[str] = None, 
        json_mode: bool = False,
        model: Optional[str] = None,
        agent_name: Optional[str] = None
    ) -> str:
        """
        Generate a response from OpenAI with retry logic.
        
        Args:
            prompt: User prompt
            system_instruction: System instruction
            json_mode: Whether to force JSON response
            model: Override model (optional)
            agent_name: Agent name for automatic model selection (optional)
        """
        # Determine model to use
        if model:
            use_model = model
        elif agent_name:
            use_model = get_model_for_agent(agent_name)
        else:
            use_model = self.default_model
            
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        settings = get_settings()
        retries = settings.api_retry_attempts
        last_error = None

        for attempt in range(retries):
            try:
                # logger.debug(f"LLM call with model={use_model}, agent={agent_name}")
                response = self.client.chat.completions.create(
                    model=use_model,
                    messages=messages,
                    response_format={"type": "json_object"} if json_mode else None
                )
                return response.choices[0].message.content
                
            except (RateLimitError, APITimeoutError, APIError) as e:
                last_error = e
                wait_time = 2 ** attempt
                logger.warning(f"OpenAI API Error (Attempt {attempt+1}/{retries}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            except Exception as e:
                logger.error(f"Unexpected OpenAI Error: {e}")
                raise e
        
        logger.error(f"Failed to generate response after {retries} attempts. Last error: {last_error}")
        raise last_error or Exception("Unknown error in LLM generation")

    async def get_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI."""
        if not text:
            return []
            
        try:
            # Use small embedding model
            response = self.client.embeddings.create(
                input=text.replace("\n", " "),
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
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
    agent_name: Optional[str] = None
) -> str:
    """
    Helper function to call the singleton client.
    
    Args:
        prompt: User prompt
        system_instruction: System instruction
        json_mode: Whether to force JSON response
        agent_name: Agent name for automatic model selection
            - 'planner': Uses gpt-5-mini (best reasoning)
            - 'detection': Uses gpt-5-mini
            - 'persona': Uses gpt-4o-mini (conversational)
            - 'response': Uses gpt-5-nano (fast/cheap)
            - 'extraction': Uses gpt-5-mini
            - 'judge': Uses gpt-5-mini
    """
    client = get_llm_client()
    return client.generate_response(
        prompt=prompt, 
        system_instruction=system_instruction, 
        json_mode=json_mode,
        agent_name=agent_name
    )


async def get_embedding(text: str) -> List[float]:
    """Helper to get embeddings."""
    client = get_llm_client()
    # Ensure client is initialized
    if not hasattr(client, 'client'): 
        client = LLMClient()
    return await client.get_embedding(text)
