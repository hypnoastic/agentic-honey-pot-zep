"""
Configuration management for Agentic Honey-Pot system.
Loads settings from environment variables with sensible defaults.
Includes per-agent model selection for cost/quality optimization.
"""

import os
import logging
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # LLM Providers
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    openai_timeout: int = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))
    api_retry_attempts: int = int(os.getenv("API_RETRY_ATTEMPTS", "3"))
    
    # Per-Agent Model Selection
    planner_model: str = os.getenv("PLANNER_MODEL", "gemini-3-flash-preview")
    detection_model: str = os.getenv("DETECTION_MODEL", "gemini-3-flash-preview")
    persona_model: str = os.getenv("PERSONA_MODEL", "gemini-3-flash-preview")
    response_model: str = os.getenv("RESPONSE_MODEL", "gemini-3-flash-preview")
    extraction_model: str = os.getenv("EXTRACTION_MODEL", "gemini-3-flash-preview")
    judge_model: str = os.getenv("JUDGE_MODEL", "gemini-3-flash-preview")
    factcheck_model: str = os.getenv("FACTCHECK_MODEL", "gemini-3-flash-preview")
    
    # Embeddings (Strictly GPT)
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    
    # Logging System Status
    def validate_setup(self):
        """Validate critical settings and warn if GPT is used for agents."""
        agent_models = [
            self.planner_model, self.detection_model, self.persona_model,
            self.response_model, self.extraction_model, self.judge_model
        ]
        active_gpt = [m for m in agent_models if "gpt" in m.lower()]
        if active_gpt:
            logger.warning(f"⚠️ CAUTION: GPT based models detected for agents: {active_gpt}. Migration intended for Gemini Flash.")
        else:
            logger.info("✅ Migration Status: All agent models appear to be non-GPT (Gemini optimized).")
            
        if not self.gemini_api_key:
            logger.error("❌ CRITICAL: GEMINI_API_KEY is missing!")
        if not self.openai_api_key:
            logger.warning("⚠️ OPENAI_API_KEY is missing (required for embeddings).")

        return True

    # Serper API for Internet Verification
    serper_api_key: str = os.getenv("SERPER_API_KEY", "")
    
    # API Security
    api_secret_key: str = os.getenv("API_SECRET_KEY", "langfasthoneypot1234")
    
    # GUVI Callback
    guvi_callback_url: str = os.getenv("GUVI_CALLBACK_URL", "")
    
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

    # Dashboard
    dashboard_password: str = os.getenv("DASHBOARD_PASSWORD", "admin").strip()




@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_model_for_agent(agent_name: str) -> str:
    """
    Get the appropriate model for a specific agent.
    Enables per-agent model optimization for cost/quality balance.
    
    Args:
        agent_name: One of 'planner', 'detection', 'persona', 'response', 'extraction', 'judge', 'factcheck'
        
    Returns:
        Model name to use for this agent
    """
    settings = get_settings()
    model_map = {
        "planner": settings.planner_model,
        "detection": settings.detection_model,
        "persona": settings.persona_model,
        "response": settings.response_model,
        "extraction": settings.extraction_model,
        "judge": settings.judge_model,
        "factcheck": settings.factcheck_model,
        "summary": settings.response_model,  # Use response model for summaries
    }
    # Default to planner model if not found
    return model_map.get(agent_name, settings.planner_model)
