from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from oasis.settings import Settings

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

HEADER = "X-OASIS-Session"


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


def _start_session(client: TestClient, *, ephemeral: bool = False) -> str:
    from oasis.api.pages import load_disclosure

    token: str = client.post("/session", json={"ephemeral": ephemeral}).json()["session_id"]
    version = load_disclosure().version
    resp = client.post("/consent", json={"disclosure_version": version}, headers={HEADER: token})
    assert resp.status_code == 204, resp.text
    return token


@pytest.fixture
def start_session() -> Callable[..., str]:
    """Open a session that has accepted the current data notice, as the onboarding page does:
    start_session(client, ephemeral=False) -> token."""
    return _start_session
