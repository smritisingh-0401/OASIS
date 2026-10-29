"""Online demo mode (OASIS_DEMO=1): memory only, an honest notice, a banner on every page, and
the limits a public server needs (decision 2026-10-28)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oasis.api.app import create_app
from oasis.api.pages import load_disclosure
from oasis.settings import Settings

HEADER = "X-OASIS-Session"


@pytest.fixture
def demo(settings: Settings) -> Settings:
    # sqlite on purpose: demo mode must still write nothing to disk.
    return settings.model_copy(update={"demo": True, "storage_backend": "sqlite"})


def _start(c: TestClient, *, ephemeral: bool) -> tuple[str, bool]:
    body = c.post("/session", json={"ephemeral": ephemeral}).json()
    version = load_disclosure(demo=True).version
    resp = c.post("/consent", json={"disclosure_version": version},
                  headers={HEADER: body["session_id"]})  # fmt: skip
    assert resp.status_code == 204, resp.text
    return body["session_id"], body["ephemeral"]


def test_demo_never_saves_even_when_asked(demo: Settings) -> None:
    with TestClient(create_app(demo)) as c:
        token, ephemeral = _start(c, ephemeral=False)
        assert ephemeral is True
        turn = {"message": "work has been rough", "client_ts": "2026-10-28T10:00:00Z"}
        assert c.post("/chat", json=turn, headers={HEADER: token}).status_code == 200
        assert c.get("/session", headers={HEADER: token}).json()["ephemeral"] is True
    assert not Path(demo.db_path).exists()


@pytest.mark.parametrize("page", ["/", "/settings.html", "/trends.html", "/why.html"])
def test_every_demo_page_carries_the_banner(demo: Settings, settings: Settings, page: str) -> None:
    with TestClient(create_app(demo)) as c:
        html = c.get(page).text
    assert 'class="demo-banner"' in html
    assert "made-up" in html
    with TestClient(create_app(settings)) as c:
        assert "demo-banner" not in c.get(page).text


def test_demo_notice_says_where_messages_go() -> None:
    notice = load_disclosure(demo=True)
    text = " ".join(p for s in notice.sections for p in s.paragraphs)
    assert notice.version != load_disclosure().version
    for words in (
        "computer of the person running this test",
        "Cloudflare",
        "language model",
        "memory only",
        "made-up",
    ):
        assert words in text, words
    assert "Nothing is sent over the internet" not in text
    assert "Save on this computer" not in text


def test_demo_page_shows_the_demo_notice(demo: Settings) -> None:
    with TestClient(create_app(demo)) as c:
        html = c.get("/").text
    assert f'data-version="{load_disclosure(demo=True).version}"' in html


def test_new_sessions_are_capped(settings: Settings) -> None:
    capped = settings.model_copy(update={"max_ephemeral_sessions": 2})
    with TestClient(create_app(capped)) as c:
        for _ in range(2):
            assert c.post("/session", json={"ephemeral": True}).status_code == 201
        resp = c.post("/session", json={"ephemeral": True})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "busy"


def test_a_chunked_body_over_the_limit_is_refused(settings: Settings) -> None:
    """No Content-Length to trust: the bytes themselves are counted."""

    def chunks() -> Iterator[bytes]:
        yield b'{"message": "'
        for _ in range(settings.max_body_bytes // 1024 + 2):
            yield b"x" * 1024
        yield b'"}'

    with TestClient(create_app(settings)) as c:
        resp = c.post("/session", content=chunks(), headers={"Content-Type": "application/json"})
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "body_too_large"
    assert resp.headers["Cache-Control"] == "no-store"


def test_the_demo_page_offers_only_start_without_saving() -> None:
    """The server forces unsaved sessions; the page hides the save choice and stores the key
    where the server's answer says (sessionStorage for an unsaved session, rules F5)."""
    import oasis

    js = (Path(oasis.__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
    assert "startSaved.hidden = DEMO && !resume" in js
    assert "saveToken(token, session.ephemeral)" in js
