"""Application settings loaded from environment variables via pydantic-settings."""

from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from project root regardless of working directory
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    # Authentication
    civic_client_id: str = ""

    # Database
    database_url: str = (
        "postgresql+asyncpg://user:password@localhost:5432/portfolio_advisor"
    )
    database_pool_size: int = 5

    # Refresh scheduler
    refresh_interval_minutes: int = 30
    refresh_cycle_timeout_minutes: int = 25

    # LLM / Cerebras AI
    cerebras_api_key: str = ""
    llm_model: str = "qwen-3-235b-a22b-instruct-2507"
    llm_concurrency: int = 1
    llm_temperature: float = 0.2
    llm_delta_threshold: float = 5.0
    llm_max_tickers_per_cycle: int = 50
    # Agent loop settings
    llm_reflection_delta: float = 3.0
    llm_max_reflection_rounds: int = 2
    llm_max_tool_calls: int = 5

    @field_validator("llm_max_reflection_rounds")
    @classmethod
    def cap_reflection_rounds(cls, v: int) -> int:
        return min(v, 3)

    # Data fetching
    fetch_concurrency: int = 20
    news_api_key: str = ""
    finnhub_api_key: str = ""

    # Scoring thresholds
    score_buy_threshold: float = 35.0
    score_sell_threshold: float = 65.0

    # Tools
    tools_config_path: str = "tools_config.yaml"

    # Rate limiting
    rate_limit_default: str = "60/minute"

    # History retention
    score_history_retention_days: int = 90


settings = Settings()
