from __future__ import annotations

from pathlib import Path

import pytest

from oasis.settings import Settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm_backend="fake",
        storage_backend="memory",
        db_path=tmp_path / "oasis.db",
        request_timeout_s=5.0,
        llm_generate_timeout_s=2.0,
        guard_retry_min_budget_s=0.0,
    )
