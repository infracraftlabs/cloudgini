"""Settings from environment variables. No secrets are stored in the database."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLOUDGINI_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./cloudgini.db"
    # Comma-separated "name:role:sha256(key)". Only hashes are kept; see scripts/init-env.sh.
    api_keys: str = ""
    # Seed the simulated account on start-up (safe: synthetic data only).
    seed_simulated: bool = True
    # Comma-separated GCP project IDs to register as real accounts (read-only by default).
    gcp_projects: str = ""
    gcp_billing_table: str = ""  # project.dataset.gcp_billing_export_v1_XXXX
    rate_limit_per_minute: int = 120
    sensitive_rate_limit_per_minute: int = 10
    cors_origins: str = "http://localhost:3000"
    # Assistant: works without a key (template answers). ANTHROPIC_API_KEY enables the model.
    assistant_model: str = "claude-opus-5-5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
