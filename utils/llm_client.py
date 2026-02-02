
import logging
import time
from typing import Optional, List, Dict, Union
import openai
from openai import OpenAI, APIError, RateLimitError, APITimeoutError
from config import get_settings

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
        self.model = settings.openai_model
        self._initialized = True
        logger.info(f"LLMClient initialized with model: {self.model}")

    def generate_response(
        self, 
        prompt: str, 
        system_instruction: Optional[str] = None, 
        json_mode: bool = False,
        temperature: float = 0.7
    ) -> str:
        """
        Generate a response from OpenAI with retry logic.
        """
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        retries = settings.api_retry_attempts
        last_error = None

        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
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
        # Return empty string or raise? Raising seems safer for agents to handle or fail gracefully.
        raise last_error or Exception("Unknown error in LLM generation")

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
    temperature: float = 0.7
) -> str:
    """Helper function to call the singleton client."""
    client = get_llm_client()
    return client.generate_response(
        prompt=prompt, 
        system_instruction=system_instruction, 
        json_mode=json_mode,
        temperature=temperature
    )
