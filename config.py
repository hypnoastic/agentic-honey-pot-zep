"""
Configuration management for Agentic Honey-Pot system.
Loads settings from environment variables with sensible defaults.
"""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Google Gemini
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    gemini_timeout: int = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "30"))
    api_retry_attempts: int = int(os.getenv("API_RETRY_ATTEMPTS", "3"))
    
    # API Security
    api_secret_key: str = os.getenv("API_SECRET_KEY", "langfastgeminihoneypot1234")
    
    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # CORS
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    
    # Mock Scammer API
    mock_scammer_enabled: bool = os.getenv("MOCK_SCAMMER_ENABLED", "true").lower() == "true"
    mock_scammer_port: int = int(os.getenv("MOCK_SCAMMER_PORT", "8001"))
    
    # Agent Configuration
    max_engagement_turns: int = int(os.getenv("MAX_ENGAGEMENT_TURNS", "5"))
    scam_detection_threshold: float = float(os.getenv("SCAM_DETECTION_THRESHOLD", "0.6"))
    max_message_length: int = int(os.getenv("MAX_MESSAGE_LENGTH", "10000"))
    
    # Zep Context AI Memory
    zep_api_key: str = os.getenv("ZEP_API_KEY", "")
    zep_enabled: bool = os.getenv("ZEP_ENABLED", "true").lower() == "true"
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra environment variables


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
