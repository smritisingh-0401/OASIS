"""HTTP contract for Phase 1 endpoints (design §12) and the security envelope (rules P3, P6, F1)."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import oasis
from oasis.api.app import create_app
from oasis.llm.fake import FakeLLM
from oasis.safety.gate import SafetyStubNotAllowed
from oasis.safety.handoff import HANDOFF_REPLY
from oasis.settings import Settings
from oasis.types import ChatMessage, SafetyVerdict

HEADER = "X-OASIS-Session"
TS = "2026-10-07T10:00:00+05:30"


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings, llm=FakeLLM(replies=["What's on your mind?"]))) as c:
        yield c


def _session(client: TestClient) -> str:
    resp = client.post("/session")
    assert resp.status_code == 201
    token = resp.json()["session_id"]
    assert isinstance(token, str)
    assert len(token) >= 40
    return token


def _chat(client: TestClient, token: str | None, message: str = "hello") -> Any:
    headers = {HEADER: token} if token else {}
    return client.post("/chat", json={"message": message, "client_ts": TS}, headers=headers)


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["llm"] == "up"
    assert body["storage"] == "up"


def test_multi_turn_chat_and_history(client: TestClient) -> None:
    token = _session(client)
    for text in ("first", "second"):
        resp = _chat(client, token, text)
        assert resp.status_code == 200
        body = resp.json()
        assert body["reply"] == "What's on your mind?"
        assert body["mode"] == "companion"
        assert body["persisted"] is True

    history = client.get("/history", headers={HEADER: token}).json()["turns"]
    assert [(t["role"], t["content"]) for t in history] == [
        ("user", "first"),
        ("assistant", "What's on your mind?"),
        ("user", "second"),
        ("assistant", "What's on your mind?"),
    ]


def test_history_limit(client: TestClient) -> None:
    token = _session(client)
    _chat(client, token, "a")
    _chat(client, token, "b")
    turns = client.get("/history?limit=1", headers={HEADER: token}).json()["turns"]
    assert [t["content"] for t in turns] == ["What's on your mind?"]


@pytest.mark.parametrize("token", [None, "not-a-real-session"])
def test_chat_requires_a_valid_session(client: TestClient, token: str | None) -> None:
    resp = _chat(client, token)
    assert resp.status_code == 401
    assert resp.json() == {
        "error": {"code": "invalid_session", "message": resp.json()["error"]["message"]}
    }


def test_history_requires_a_valid_session(client: TestClient) -> None:
    resp = client.get("/history", headers={HEADER: "nope"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_session"


@pytest.mark.parametrize(
    "body",
    [
        {"message": "", "client_ts": TS},
        {"message": "x" * 2001, "client_ts": TS},
        {"message": "hi"},
        {"message": "hi", "client_ts": "yesterday"},
        {"message": "hi", "client_ts": TS, "unexpected": 1},
    ],
)
def test_invalid_turns_get_typed_422(client: TestClient, body: dict[str, Any]) -> None:
    token = _session(client)
    resp = client.post("/chat", json=body, headers={HEADER: token})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_turn"
    # Validation errors must not echo the submitted text back into responses or logs.
    assert "x" * 50 not in resp.text


def test_oversized_body_is_rejected(client: TestClient) -> None:
    token = _session(client)
    resp = client.post(
        "/chat",
        content=b'{"message": "' + b"a" * 20_000 + b'"}',
        headers={HEADER: token, "content-type": "application/json"},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "body_too_large"


def test_unknown_route_uses_error_shape(client: TestClient) -> None:
    resp = client.get("/api/nothing-here")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("path", ["/health", "/", "/app.js", "/api/nothing-here"])
def test_security_headers_on_every_response(client: TestClient, path: str) -> None:
    headers = client.get(path).headers
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in headers["content-security-policy"]
    assert "script-src 'self'" in headers["content-security-policy"]
    assert "camera=()" in headers["permissions-policy"]


def test_chat_page_has_help_card_and_dev_banner(client: TestClient) -> None:
    html = client.get("/").text
    assert "Need help now?" in html
    assert "Development build" in html
    assert "not a diagnosis" in html


def test_web_assets_make_no_external_requests() -> None:
    web = Path(oasis.__file__).parent / "web"
    files = [p for p in web.rglob("*") if p.is_file()]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(https?:)?//[a-z0-9.-]+\.[a-z]{2,}", text, re.I), path.name
        assert "innerHTML" not in text, path.name


def test_session_token_never_travels_in_urls() -> None:
    js = (Path(oasis.__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
    assert "?session" not in js.lower()
    assert HEADER in js


# --- shortcut and failure paths through HTTP -------------------------------------


class AlwaysCrisis:
    is_stub = False

    def check(self, text: str) -> SafetyVerdict:
        return SafetyVerdict(is_crisis=True, tiers=frozenset({"explicit"}))


def test_crisis_is_answered_even_without_a_session(settings: Settings) -> None:
    with TestClient(create_app(settings, safety=AlwaysCrisis())) as c:
        resp = _chat(c, None)
    assert resp.status_code == 200
    assert resp.json()["mode"] == "crisis"
    assert resp.json()["reply"] == HANDOFF_REPLY


def test_unexpected_engine_error_returns_templated_reply(settings: Settings) -> None:
    class Weird(FakeLLM):
        async def generate(
            self, messages: Sequence[ChatMessage], *, max_tokens: int, timeout_s: float
        ) -> str:
            raise ValueError("bug")

    with TestClient(create_app(settings, llm=Weird())) as c:
        resp = _chat(c, _session(c))
    assert resp.status_code == 200
    assert resp.json()["templated"] is True
    assert "internal.error" in resp.json()["degraded"]


def test_stub_safety_refuses_to_start_without_dev_flag(settings: Settings) -> None:
    with pytest.raises(SafetyStubNotAllowed):
        create_app(settings.model_copy(update={"dev_mode": False}))


def test_history_survives_restart(settings: Settings) -> None:
    on_disk = settings.model_copy(update={"storage_backend": "sqlite"})
    with TestClient(create_app(on_disk, llm=FakeLLM(replies=["ok"]))) as c:
        token = _session(c)
        _chat(c, token, "remember me")

    with TestClient(create_app(on_disk)) as c:
        turns = c.get("/history", headers={HEADER: token}).json()["turns"]
    assert [t["content"] for t in turns] == ["remember me", "ok"]


def test_default_llm_backend_is_llama_server(settings: Settings) -> None:
    app = create_app(
        settings.model_copy(update={"llm_backend": "llama_server", "llm_url": "http://127.0.0.1:9"})
    )
    with TestClient(app) as c:
        assert c.get("/health").json()["llm"] == "down"
        resp = _chat(c, _session(c))
    assert resp.json()["templated"] is True
