from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional
import os

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # GitHub App Configuration
    GITHUB_APP_ID: str = "test_app_id"
    GITHUB_PRIVATE_KEY_PATH: str = "test_key.pem"
    GITHUB_PRIVATE_KEY: Optional[str] = None  # For Railway deployment
    GITHUB_WEBHOOK_SECRET: str = "test_secret"
    
    # Helper property to check if GitHub App is configured
    @property
    def has_real_github_app(self) -> bool:
        """Check if GitHub App is configured with real values"""
        return (
            self.GITHUB_APP_ID != "test_app_id" and
            self.GITHUB_WEBHOOK_SECRET != "test_secret" and
            (self.GITHUB_PRIVATE_KEY is not None or self.GITHUB_PRIVATE_KEY_PATH != "test_key.pem")
        )
    
    # Claude API Configuration
    ANTHROPIC_API_KEY: str = "test_api_key"
    
    # Database Configuration
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/ci_sage"
    REDIS_URL: str = "redis://localhost:6379"
    
    # Railway-specific configuration
    @property
    def railway_database_url(self) -> str:
        """Get Railway PostgreSQL URL if available"""
        # Railway provides DATABASE_URL automatically when PostgreSQL service is added
        return os.getenv("DATABASE_URL", self.DATABASE_URL)
    
    # Application Configuration
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    WEBHOOK_PORT: int = 8000
    
    # Optional: Custom analysis prompts
    CUSTOM_ANALYSIS_PROMPT: Optional[str] = None
    CUSTOM_REMEDIATION_PROMPT: Optional[str] = None
    
    # Helper properties
    @property
    def is_production(self) -> bool:
        """Check if running in production with real credentials"""
        return (
            self.APP_ENV == "production" and
            self.ANTHROPIC_API_KEY != "test_api_key" and
            self.GITHUB_APP_ID != "test_app_id"
        )
    
    @property
    def has_real_claude_key(self) -> bool:
        """Check if Claude API key is real (not test value)"""
        return self.ANTHROPIC_API_KEY != "test_api_key"
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

# Global settings instance
settings = Settings()
