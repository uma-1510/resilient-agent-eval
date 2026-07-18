from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str
    model_name: str = "gemini-2.0-flash"
    retry_budget: int = 3
    sandbox_mem_limit: str = "128m"
    sandbox_timeout_seconds: int = 5
    sandbox_nano_cpus: int = 1_000_000_000


@lru_cache
def get_settings() -> Settings:
    """Lazily loaded and cached so importing this module never requires a .env
    to already exist — only code paths that actually need config (the LLM
    client, the sandbox, main.py) pay the cost of validation, and a missing
    GEMINI_API_KEY fails fast with a clear pydantic error at that point."""
    return Settings()
