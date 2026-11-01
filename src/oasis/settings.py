"""Typed configuration. Every tunable value lives here, read from OASIS_* environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OASIS_", env_file=".env", extra="ignore")

    storage_backend: Literal["sqlite", "memory"] = "sqlite"
    db_path: Path = Path("data/oasis.db")
    sqlite_busy_timeout_ms: int = Field(2000, ge=0)

    llm_backend: Literal["llama_server", "fake"] = "llama_server"
    llm_url: str = "http://127.0.0.1:8080"
    llm_model: str = "qwen3.5-4b-q4_k_m"
    llm_connect_timeout_s: float = Field(1.0, gt=0)
    llm_generate_timeout_s: float = Field(20.0, gt=0)
    llm_max_concurrency: int = Field(1, ge=1)
    llm_queue_limit: int = Field(2, ge=0)
    llm_max_tokens: int = Field(160, ge=1)
    llm_temperature: float = 0.7
    llm_top_p: float = 0.8
    llm_top_k: int = 20
    llm_min_p: float = 0.0

    request_timeout_s: float = Field(30.0, gt=0)
    guard_retry_min_budget_s: float = Field(8.0, ge=0)
    history_turns: int = Field(6, ge=0)
    crisis_classifier: bool = True
    guard_nli_dir: Path = Path("models/nli")
    psychoed_embed_dir: Path = Path("models/embed")
    max_body_bytes: int = Field(16 * 1024, ge=1024)

    ephemeral_idle_timeout_s: float = Field(2 * 3600, gt=0)
    saved_idle_expiry_days: int = Field(90, gt=0)
    max_ephemeral_sessions: int = Field(1000, ge=1)

    demo: bool = False
