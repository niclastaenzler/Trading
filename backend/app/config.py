"""Application settings, loaded from environment variables.

All operational/secret values live here. Trading *behaviour* (risk, strategy,
compliance) is configured per-user in the database — see `app.models.config`
and `app.services.config_defaults`.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- App ---
    app_env: str = "development"
    app_name: str = "AI Trading Platform"
    api_port: int = 8000

    # --- Security ---
    jwt_secret_key: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    # Fernet key for encrypting broker credentials at rest.
    encryption_key: str = ""

    # --- Database / cache ---
    database_url: str = "postgresql+asyncpg://trading:trading@localhost:5432/trading"
    redis_url: str = "redis://localhost:6379/0"

    # --- Broker ---
    broker: str = "paper"  # paper | capital_com
    capital_com_api_key: str = ""
    capital_com_identifier: str = ""
    capital_com_password: str = ""
    capital_com_demo: bool = True

    # --- Integrations ---
    tradingview_webhook_secret: str = "change-me"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- CORS ---
    # Accept a comma-separated string from the env (e.g.
    # "https://user.github.io,http://localhost:3000"). NoDecode stops
    # pydantic-settings from trying to JSON-decode it first.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
