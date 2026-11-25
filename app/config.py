"""Environment-based application configuration."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COMBINELLM_", env_file=".env", extra="ignore")

    app_name: str = "CombineLLM"
    environment: Literal["development", "test", "production"] = "development"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = Field(default="", pattern=r"^[a-zA-Z0-9._-]*$", max_length=100)
    provider_timeout_seconds: float = Field(default=60, ge=1, le=300)
