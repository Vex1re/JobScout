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
    SOFT_MATCH_SCORE: int = Field(default=35, description="Soft fallback match threshold for adaptive mode")
    MIN_DESIRED_MATCHES: int = Field(default=15, description="Minimum desired match count before activating adaptive mode")
    RED_FLAG_STRICT_MODE: bool = Field(default=True, description="Block jobs marked with high scam risk")

    # Scraping configuration
    USER_AGENT: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        description="User-Agent header for HTTP requests"
    )
    REQUEST_TIMEOUT: int = Field(default=15, description="Timeout for external requests in seconds")

    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Pagination & limits
    VACANCIES_PER_PAGE: int = Field(default=5, description="Number of vacancies per page in Telegram inline list")
    MAX_VACANCIES_PER_SOURCE: int = Field(default=50, description="Max vacancies to parse per aggregator per cycle")

    # Aggregator API Keys
    SUPERJOB_API_KEY: Optional[str] = Field(default=None, description="SuperJob API secret / App ID")

    # Proxy settings
    PROXY_URL: Optional[str] = Field(
        default=None,
        description="Optional HTTP/SOCKS5 proxy URL (e.g. socks5://user:pass@host:port or http://host:port)"
    )

    # Environment & Bot Execution Mode
    ENV: str = Field(default="dev", description="Environment mode: 'dev' or 'prod'")
    BOT_MODE: str = Field(default="polling", description="Bot run mode: 'polling' or 'webhook'")
    WEBHOOK_URL: Optional[str] = Field(default=None, description="Public HTTPS URL for Telegram webhook")
    WEBHOOK_PATH: str = Field(default="/webhook", description="Path for Telegram webhook requests")
    WEBHOOK_HOST: str = Field(default="0.0.0.0", description="Host to bind webhook server")
    WEBHOOK_PORT: int = Field(default=8080, description="Port to bind webhook server")
    WEBHOOK_SECRET: Optional[str] = Field(default=None, description="Optional secret token for Telegram webhook")

    # Database Pool Settings
    DB_POOL_SIZE: int = Field(default=10, description="SQLAlchemy connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=5, description="SQLAlchemy connection pool max overflow")
    DB_POOL_TIMEOUT: int = Field(default=30, description="SQLAlchemy connection pool timeout in seconds")
    DB_POOL_RECYCLE: int = Field(default=1800, description="SQLAlchemy connection pool recycle in seconds")
    SQLITE_BUSY_TIMEOUT: int = Field(default=5000, description="SQLite busy timeout in milliseconds")

    # Redis (for FSM, rate limiting, and queues)
    REDIS_URL: Optional[str] = Field(
        default=None,
        description="Redis URL (e.g. redis://localhost:6379/0). Required for prod."
    )

    # Throttling & Rate Limiting
    THROTTLE_RATE_LIMIT: float = Field(
        default=0.8,
        description="Minimum interval in seconds between user actions"
    )


settings = Settings()
