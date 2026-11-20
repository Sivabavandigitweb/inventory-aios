from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings with safe local defaults."""

    app_name: str = "Inventory AIOS API"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    api_version: str = "v1"
    frontend_origin: str = "http://localhost:5173"
    log_level: str = "INFO"
    app_version: str = "0.1.0"
    database_url: str | None = None
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_pre_ping: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="INVENTORY_",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()