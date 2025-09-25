from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # GitHub App Configuration
    GITHUB_APP_ID: str
    GITHUB_PRIVATE_KEY_PATH: str
    GITHUB_WEBHOOK_SECRET: str
    
    # Claude API Configuration
    ANTHROPIC_API_KEY: str
    
    # Database Configuration
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/ci_sage"
    REDIS_URL: str = "redis://localhost:6379"
    
    # Application Configuration
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    WEBHOOK_PORT: int = 8000
    
    # Optional: Custom analysis prompts
    CUSTOM_ANALYSIS_PROMPT: Optional[str] = None
    CUSTOM_REMEDIATION_PROMPT: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Global settings instance
settings = Settings()
