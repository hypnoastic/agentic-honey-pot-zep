"""
Configuration management for Agentic Honey-Pot system.
Loads settings from environment variables with sensible defaults.
Includes per-agent model selection for cost/quality optimization.
"""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_timeout: int = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))
    api_retry_attempts: int = int(os.getenv("API_RETRY_ATTEMPTS", "3"))
    
    # Per-Agent Model Selection (GPT-5 family fallback)
    # Per-Agent Model Selection (GPT-5 family)
    model_planner: str = os.getenv("OPENAI_MODEL_PLANNER", "gpt-4o-mini")  # Best reasoning
    model_detection: str = os.getenv("OPENAI_MODEL_DETECTION", "gpt-3.5-turbo")
    model_persona: str = os.getenv("OPENAI_MODEL_PERSONA", "gpt-4o-mini") # Conversational
    model_response: str = os.getenv("OPENAI_MODEL_RESPONSE", "gpt-3.5-turbo")  # Cheapest
    model_extraction: str = os.getenv("OPENAI_MODEL_EXTRACTION", "gpt-4o-mini")
    model_judge: str = os.getenv("OPENAI_MODEL_JUDGE", "gpt-4o-mini")
    
    # Serper API for Internet Verification
    serper_api_key: str = os.getenv("SERPER_API_KEY", "")
    
    # API Security
    api_secret_key: str = os.getenv("API_SECRET_KEY", "langfasthoneypot1234")
    
    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    # CORS
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    
    # Agent Configuration
    max_engagement_turns: int = int(os.getenv("MAX_ENGAGEMENT_TURNS", "5"))
    scam_detection_threshold: float = float(os.getenv("SCAM_DETECTION_THRESHOLD", "0.6"))
    max_message_length: int = int(os.getenv("MAX_MESSAGE_LENGTH", "10000"))
    
    # Postgres Memory (Neon)
    database_url: str = os.getenv("DATABASE_URL", "")
    postgres_enabled: bool = os.getenv("POSTGRES_ENABLED", "true").lower() == "true"
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "DEBUG")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_model_for_agent(agent_name: str) -> str:
    """
    Get the appropriate model for a specific agent.
    Enables per-agent model optimization for cost/quality balance.
    
    Args:
        agent_name: One of 'planner', 'detection', 'persona', 'response', 'extraction', 'judge'
        
    Returns:
        Model name to use for this agent
    """
    settings = get_settings()
    model_map = {
        "planner": settings.model_planner,
        "detection": settings.model_detection,
        "persona": settings.model_persona,
        "response": settings.model_response,
        "extraction": settings.model_extraction,
        "judge": settings.model_judge,
    }
    return model_map.get(agent_name, settings.openai_model)
