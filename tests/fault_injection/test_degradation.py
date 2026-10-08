"""Every request ends in a real or fallback reply inside the hard timeout (PRD L10)."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from oasis.api.app import create_app
from oasis.llm.fake import FakeLLM
from oasis.safety.handoff import HANDOFF_REPLY
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.storage.repository import StorageUnavailable

HEADER = "X-OASIS-Session"


class DeadRepo(MemoryRepository):
    async def get_session(self, session_hash: str) -> Any:
        raise StorageUnavailable

    async def create_user_session(self, session_hash: str) -> str:
        raise StorageUnavailable

    async def ping(self) -> bool:
        return False


def _post(c: TestClient, token: str = "unknown-session") -> Any:  # noqa: S107
    return c.post(
        "/chat",
        json={"message": "hi", "client_ts": "2026-10-07T10:00:00Z"},
        headers={HEADER: token},
    )


@pytest.mark.parametrize("fail", ["down", "timeout", "http_error", "empty", "busy"])
def test_llm_failures_answer_with_template(settings: Settings, fail: str) -> None:
    with TestClient(create_app(settings, llm=FakeLLM(fail=fail))) as c:
        token = c.post("/session").json()["session_id"]
        resp = _post(c, token)
    assert resp.status_code == 200
    assert resp.json()["templated"] is True


def test_hung_llm_answers_within_request_timeout(settings: Settings) -> None:
    fast = settings.model_copy(update={"request_timeout_s": 1.0, "llm_generate_timeout_s": 30})
    with TestClient(create_app(fast, llm=FakeLLM(delay_s=60))) as c:
        token = c.post("/session").json()["session_id"]
        start = time.monotonic()
        resp = _post(c, token)
        elapsed = time.monotonic() - start
    assert resp.status_code == 200
    assert resp.json()["templated"] is True
    assert elapsed < 3.0  # far below the 60 s hang; slack absorbs a loaded test machine


def test_storage_down_still_answers_chat(settings: Settings) -> None:
    with TestClient(create_app(settings, repo=DeadRepo())) as c:
        resp = _post(c)
        assert c.get("/health").json()["storage"] == "down"
    assert resp.status_code == 200
    assert resp.json()["reply"]
    assert resp.json()["persisted"] is False
    assert "storage.down" in resp.json()["degraded"]


def test_storage_down_session_and_history_return_503(settings: Settings) -> None:
    with TestClient(create_app(settings, repo=DeadRepo())) as c:
        assert c.post("/session").json()["error"]["code"] == "storage_unavailable"
        resp = c.get("/history", headers={HEADER: "t"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "storage_unavailable"


class UntouchableLLM(FakeLLM):
    async def generate(self, *args: Any, **kwargs: Any) -> str:
        raise AssertionError("a crisis turn must not reach the LLM")


@pytest.mark.parametrize("token", ["unknown-session", ""])
def test_crisis_handoff_survives_dead_storage_and_dead_llm(settings: Settings, token: str) -> None:
    with TestClient(create_app(settings, llm=UntouchableLLM(), repo=DeadRepo())) as c:
        resp = c.post(
            "/chat",
            json={"message": "I want to end my life", "client_ts": "2026-10-07T10:00:00Z"},
            headers={HEADER: token} if token else {},
        )
    assert resp.status_code == 200
    assert resp.json()["mode"] == "crisis"
    assert resp.json()["reply"] == HANDOFF_REPLY
