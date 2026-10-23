"""Privacy over HTTP (Phase 10): consent gate, saved or ephemeral sessions, export, delete."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from oasis.api.app import create_app
from oasis.api.pages import load_disclosure
from oasis.llm.fake import FakeLLM
from oasis.safety.handoff import HANDOFF_REPLY
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository

HEADER = "X-OASIS-Session"
TS = "2026-10-23T10:00:00+05:30"
MARKER = "zqx-privacy-marker lantern"


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings, llm=FakeLLM())) as c:
        yield c


def _chat(c: TestClient, token: str, message: str = "hello") -> Any:
    return c.post("/chat", json={"message": message, "client_ts": TS}, headers={HEADER: token})


def _new(c: TestClient, **body: Any) -> str:
    resp = c.post("/session", json=body)
    assert resp.status_code == 201
    token: str = resp.json()["session_id"]
    return token


def _consent(c: TestClient, token: str, version: str | None = None) -> Any:
    version = version or load_disclosure().version
    return c.post("/consent", json={"disclosure_version": version}, headers={HEADER: token})


# --- consent gate --------------------------------------------------------------------------


def test_chat_is_refused_before_consent(client: TestClient) -> None:
    token = _new(client)
    resp = _chat(client, token)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "consent_required"
    assert _consent(client, token).status_code == 204
    assert _chat(client, token).status_code == 200


def test_a_crisis_is_answered_before_consent(client: TestClient) -> None:
    resp = _chat(client, _new(client), "I want to kill myself")
    assert resp.status_code == 200
    assert resp.json()["reply"] == HANDOFF_REPLY


def test_consent_must_name_the_current_notice(client: TestClient) -> None:
    token = _new(client)
    assert _consent(client, token, "0-old").status_code == 422
    assert _chat(client, token).status_code == 403
    assert _consent(client, "not-a-session").status_code == 401


def test_session_reports_its_mode_and_consent(client: TestClient) -> None:
    saved, temp = _new(client), _new(client, ephemeral=True)
    assert client.post("/session").json()["ephemeral"] is False  # no body: saved, as before
    info = client.get("/session", headers={HEADER: temp}).json()
    assert info == {"ephemeral": True, "consented": False,
                    "disclosure_version": load_disclosure().version}  # fmt: skip
    _consent(client, saved)
    assert client.get("/session", headers={HEADER: saved}).json()["consented"] is True
    assert client.get("/session").status_code == 401


def test_consent_is_audited_in_saved_mode(settings: Settings) -> None:
    repo = MemoryRepository()
    with TestClient(create_app(settings, repo=repo)) as c:
        token = _new(c)
        _consent(c, token)
        export = c.get("/export", headers={HEADER: token}).json()
    assert [a["event"] for a in export["tables"]["audit_log"]] == ["consent_given"]
    assert json.loads(export["tables"]["audit_log"][0]["detail"]) == {
        "disclosure_version": load_disclosure().version
    }


# --- export --------------------------------------------------------------------------------


@pytest.mark.parametrize("ephemeral", [False, True])
def test_export_downloads_everything_the_user_said(
    client: TestClient, start_session: Callable[..., str], ephemeral: bool
) -> None:
    token = start_session(client, ephemeral=ephemeral)
    other = start_session(client)
    _chat(client, token, MARKER)
    _chat(client, other, "someone else's words")
    resp = client.get("/export", headers={HEADER: token})
    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == 'attachment; filename="oasis-export.json"'
    assert resp.headers["cache-control"] == "no-store"
    body = resp.json()
    assert body["format"] == "oasis-export/1"
    assert body["ephemeral"] is ephemeral
    assert MARKER in [t["content"] for t in body["tables"]["turns"]]
    assert "someone else" not in resp.text
    assert token not in resp.text  # the bearer token is never stored, so never exported


def test_export_needs_a_session(client: TestClient) -> None:
    assert client.get("/export").status_code == 401


# --- delete --------------------------------------------------------------------------------


@pytest.mark.parametrize("ephemeral", [False, True])
def test_delete_needs_confirmation_then_removes_everything(
    client: TestClient, start_session: Callable[..., str], ephemeral: bool
) -> None:
    token = start_session(client, ephemeral=ephemeral)
    _chat(client, token, MARKER)
    headers = {HEADER: token}
    assert client.request("DELETE", "/account", json={"confirm": "yes"}, headers=headers
                          ).status_code == 422  # fmt: skip
    assert client.get("/session", headers=headers).status_code == 200
    assert client.request("DELETE", "/account", json={"confirm": "DELETE"}, headers=headers
                          ).status_code == 204  # fmt: skip
    for path in ("/session", "/history", "/export", "/trends"):
        assert client.get(path, headers=headers).status_code == 401, path
    assert _chat(client, token).status_code == 401
    assert _chat(client, token, "I want to kill myself").json()["reply"] == HANDOFF_REPLY


def test_delete_needs_a_session(client: TestClient) -> None:
    assert client.request("DELETE", "/account", json={"confirm": "DELETE"}).status_code == 401


def _on_disk(settings: Settings, tmp_path: Path) -> Settings:
    return settings.model_copy(update={"storage_backend": "sqlite", "db_path": tmp_path / "o.db"})


def test_deleted_words_are_gone_from_the_database_files(
    settings: Settings, tmp_path: Path, start_session: Callable[..., str]
) -> None:
    with TestClient(create_app(_on_disk(settings, tmp_path), llm=FakeLLM())) as c:
        token = start_session(c)
        for _ in range(3):
            _chat(c, token, MARKER)
        files = sorted(tmp_path.glob("o.db*"))
        assert any(MARKER.encode() in f.read_bytes() for f in files)  # sanity: it was written
        c.request("DELETE", "/account", json={"confirm": "DELETE"}, headers={HEADER: token})
        for f in sorted(tmp_path.glob("o.db*")):
            assert MARKER.encode() not in f.read_bytes(), f.name
    for f in sorted(tmp_path.glob("o.db*")):
        assert MARKER.encode() not in f.read_bytes(), f.name


def test_logs_hold_no_content_through_consent_export_and_delete(
    client: TestClient, start_session: Callable[..., str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    token = start_session(client)
    _chat(client, token, MARKER)
    client.get("/export", headers={HEADER: token})
    client.request("DELETE", "/account", json={"confirm": "DELETE"}, headers={HEADER: token})
    assert MARKER not in caplog.text
    assert "lantern" not in caplog.text
    assert token not in caplog.text


# --- ephemeral mode leaves no trace on disk (rules P4) ------------------------------------


def _snapshot(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}  # fmt: skip


def test_an_ephemeral_session_changes_no_file(
    settings: Settings, tmp_path: Path, start_session: Callable[..., str]
) -> None:
    with TestClient(create_app(_on_disk(settings, tmp_path), llm=FakeLLM())) as c:
        before = _snapshot(tmp_path)
        token = start_session(c, ephemeral=True)
        for text in (MARKER, "I always mess everything up", "what's wrong with me"):
            assert _chat(c, token, text).status_code == 200
        eid = _chat(c, token).json()["explanation_id"]
        assert c.get(f"/explanations/{eid}", headers={HEADER: token}).status_code == 200
        assert c.get("/trends", headers={HEADER: token}).status_code == 200
        assert c.get("/export", headers={HEADER: token}).status_code == 200
        assert c.get("/history", headers={HEADER: token}).json()["turns"]
        c.request("DELETE", "/account", json={"confirm": "DELETE"}, headers={HEADER: token})
        assert _snapshot(tmp_path) == before


# --- pages ---------------------------------------------------------------------------------


def test_onboarding_is_on_the_chat_page(client: TestClient) -> None:
    page = client.get("/").text
    d = load_disclosure()
    assert f'data-version="{d.version}"' in page
    assert d.title in page
    assert "Start without saving" in page
    assert 'href="settings.html"' in page
    assert 'id="help"' in page  # "Need help now?" stays reachable before consent


def test_settings_page_offers_export_and_delete(client: TestClient) -> None:
    page = client.get("/settings.html")
    assert page.status_code == 200
    assert 'src="settings.js"' in page.text
    for words in ("Export", "Delete"):
        assert words in page.text
    js = client.get("/settings.js").text
    assert "/export" in js
    assert "/account" in js
    assert '"DELETE"' in js


def test_chat_page_script_handles_consent() -> None:
    import oasis

    js = (Path(oasis.__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
    assert "/consent" in js
    assert "consent_required" in js
    assert '"/session"' in js
