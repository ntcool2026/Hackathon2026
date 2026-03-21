"""Application settings loaded from environment variables via pydantic-settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Authentication
    civic_client_id: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/portfolio_advisor"
    database_pool_size: int = 5

    # Refresh scheduler
    refresh_interval_minutes: int = 30
    refresh_cycle_timeout_minutes: int = 25

    # LLM / OpenRouter
    openrouter_api_key: str = ""
    llm_model: str = "mistralai/mistral-7b-instruct"
    llm_concurrency: int = 1
    llm_max_iterations: int = 6
    llm_temperature: float = 0.2
    llm_react_prompt_file: str = ""
    llm_delta_threshold: float = 5.0
    llm_max_tickers_per_cycle: int = 50
    llm_max_context_chars: int = 2000

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
