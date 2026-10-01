import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Telegram Bot Token
    BOT_TOKEN: str = Field(default="", description="Telegram Bot token from @BotFather")

    # Database
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./job_hunter.db",
        description="Async SQLAlchemy database URL (SQLite or PostgreSQL)"
    )

    # Admin IDs for management commands / alerts
    ADMIN_IDS: List[int] = Field(default_factory=list, description="List of Telegram admin IDs")

    # Optional AI/LLM for advanced matching & smart summarization
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key or compatible provider")
    OPENAI_BASE_URL: str = Field(default="https://api.openai.com/v1", description="OpenAI API base URL")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="LLM model name")

    # Background polling & alerts
    ENABLE_AUTO_NOTIFICATIONS: bool = Field(default=True, description="Enable background automated search")
    AUTO_SEARCH_INTERVAL_MINUTES: int = Field(default=30, description="Interval for auto parsing new jobs in minutes")

    # Scoring & Red flag thresholds
    MIN_MATCH_SCORE: int = Field(default=45, description="Minimum match percentage to present to user")
    RED_FLAG_STRICT_MODE: bool = Field(default=True, description="Block jobs marked with high scam risk")

    # Scraping configuration
    USER_AGENT: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        description="User-Agent header for HTTP requests"
    )
    REQUEST_TIMEOUT: int = Field(default=15, description="Timeout for external requests in seconds")

    # Pagination & limits
    VACANCIES_PER_PAGE: int = Field(default=5, description="Number of vacancies per page in Telegram inline list")
    MAX_VACANCIES_PER_SOURCE: int = Field(default=30, description="Max vacancies to parse per aggregator per cycle")


settings = Settings()
