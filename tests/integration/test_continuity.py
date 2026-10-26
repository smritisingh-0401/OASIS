"""Session continuity (PRD L9, Phase 13): a saved conversation carries on after OASIS restarts,
an unsaved one does not, and a saved one with no message for 90 days is deleted."""

from __future__ import annotations

import datetime
import sqlite3
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from oasis.api.app import create_app
from oasis.llm.fake import FakeLLM
from oasis.router.weights import config as router_config
from oasis.settings import Settings

HEADER = "X-OASIS-Session"
TS = "2026-10-26T10:00:00Z"
DISTORTED = "I'm such a failure, I always mess everything up"


@pytest.fixture
def on_disk(settings: Settings) -> Settings:
    return settings.model_copy(update={"storage_backend": "sqlite"})


def _chat(c: TestClient, token: str, message: str, action: dict[str, Any] | None = None) -> Any:
    body: dict[str, Any] = {"message": message, "client_ts": TS}
    if action is not None:
        body["action"] = action
    resp = c.post("/chat", json=body, headers={HEADER: token})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _history(c: TestClient, token: str) -> Any:
    return c.get("/history", headers={HEADER: token})


def _answer(item: int) -> dict[str, Any]:
    return {"type": "assessment_answer", "value": 0, "instrument": "PHQ9", "item": item}


def test_an_open_questionnaire_carries_on_after_a_restart(
    on_disk: Settings, start_session: Callable[..., str]
) -> None:
    with TestClient(create_app(on_disk)) as c:
        token = start_session(c)
        _chat(c, token, "can I take a depression test?")
        _chat(c, token, "Yes", {"type": "assessment_consent", "accept": True})
        _chat(c, token, "Not at all", _answer(1))
        _chat(c, token, "Not at all", _answer(2))

    with TestClient(create_app(on_disk)) as c:
        card = _history(c, token).json()["assessment"]
        assert (card["step"], card["item"]) == ("item", 3)
        nxt = _chat(c, token, "Not at all", _answer(3))
    assert (nxt["assessment"]["step"], nxt["assessment"]["item"]) == ("item", 4)


def test_an_exercise_carries_on_at_its_step_after_a_restart(
    on_disk: Settings, start_session: Callable[..., str]
) -> None:
    with TestClient(create_app(on_disk)) as c:
        token = start_session(c)
        for _ in range(router_config().hysteresis_turns):
            _chat(c, token, DISTORTED)
        first = _chat(c, token, "Yes, let's try", {"type": "exercise_consent", "accept": True})
        assert (first["mode"], first["exercise"]["item"]) == ("cbt", 1)

    with TestClient(create_app(on_disk)) as c:
        assert _history(c, token).json()["exercise"]["item"] == 1
        second = _chat(c, token, "It's the thought that I always get things wrong")
    assert (second["mode"], second["exercise"]["item"]) == ("cbt", 2)


def test_post_crisis_mode_holds_after_a_restart(
    on_disk: Settings, start_session: Callable[..., str]
) -> None:
    with TestClient(create_app(on_disk)) as c:
        token = start_session(c)
        assert _chat(c, token, "I want to kill myself")["mode"] == "crisis"

    with TestClient(create_app(on_disk, llm=FakeLLM())) as c:
        assert _chat(c, token, "ok")["mode"] == "post_crisis"


def test_the_chosen_style_holds_after_a_restart(
    on_disk: Settings, start_session: Callable[..., str]
) -> None:
    chosen = {"directness": "indirect", "formality": "formal", "country": "GB"}
    with TestClient(create_app(on_disk)) as c:
        token = start_session(c)
        assert c.put("/settings", json=chosen, headers={HEADER: token}).status_code == 200

    with TestClient(create_app(on_disk)) as c:
        assert c.get("/settings", headers={HEADER: token}).json() == chosen


def test_an_unsaved_conversation_is_gone_after_a_restart(
    on_disk: Settings, start_session: Callable[..., str]
) -> None:
    with TestClient(create_app(on_disk)) as c:
        token = start_session(c, ephemeral=True)
        _chat(c, token, "just between us")
        assert _history(c, token).status_code == 200

    with TestClient(create_app(on_disk)) as c:
        assert _history(c, token).status_code == 401


def _age(db: Any, token_hash: str, days: int) -> None:
    then = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE sessions SET last_seen_at = ?, created_at = ? WHERE session_id_hash = ?",
            (then, then, token_hash),
        )


def test_a_saved_conversation_unused_for_90_days_is_deleted_at_startup(
    on_disk: Settings, start_session: Callable[..., str]
) -> None:
    from oasis.api.routes import hash_token

    with TestClient(create_app(on_disk)) as c:
        old, recent = start_session(c), start_session(c)
        _chat(c, old, "an old conversation")
        _chat(c, recent, "a recent one")
    _age(on_disk.db_path, hash_token(old), on_disk.saved_idle_expiry_days + 1)
    _age(on_disk.db_path, hash_token(recent), on_disk.saved_idle_expiry_days - 1)

    with TestClient(create_app(on_disk)) as c:
        assert _history(c, old).status_code == 401
        assert _history(c, recent).status_code == 200
    with sqlite3.connect(on_disk.db_path) as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        turns = conn.execute("SELECT content FROM turns").fetchall()
    assert users == 1
    assert ("an old conversation",) not in turns
    assert ("a recent one",) in turns


def test_the_expiry_is_a_setting(settings: Settings) -> None:
    assert settings.saved_idle_expiry_days == 90
    with pytest.raises(ValidationError):
        settings.model_validate({**settings.model_dump(), "saved_idle_expiry_days": 0})


def test_the_notice_says_saved_conversations_expire() -> None:
    from oasis.api.pages import load_disclosure

    text = " ".join(p for s in load_disclosure().sections for p in s.paragraphs)
    assert "90 days without a message" in text
