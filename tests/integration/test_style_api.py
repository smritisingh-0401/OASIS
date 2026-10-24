"""Settings over HTTP (Phase 11): style profile and the help card's country (FR-CUL-1, 2)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from oasis.api.app import create_app
from oasis.llm.fake import FakeLLM
from oasis.safety.resources import load_resources
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.style.framing import framing
from oasis.types import StyleProfile

HEADER = "X-OASIS-Session"
TS = "2026-10-24T10:00:00+05:30"
DEFAULTS = {"directness": "balanced", "formality": "neutral", "country": None}


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def client(settings: Settings, llm: FakeLLM) -> Iterator[TestClient]:
    with TestClient(create_app(settings, llm=llm)) as c:
        yield c


def _put(c: TestClient, token: str, **body: Any) -> Any:
    return c.put("/settings", json={**DEFAULTS, **body}, headers={HEADER: token})


def _chat(c: TestClient, token: str, message: str) -> Any:
    return c.post("/chat", json={"message": message, "client_ts": TS}, headers={HEADER: token})


@pytest.mark.parametrize("ephemeral", [False, True])
def test_settings_start_at_the_defaults_and_can_be_changed(
    client: TestClient, start_session: Callable[..., str], ephemeral: bool
) -> None:
    token = start_session(client, ephemeral=ephemeral)
    other = start_session(client)
    assert client.get("/settings", headers={HEADER: token}).json() == DEFAULTS
    chosen = {"directness": "indirect", "formality": "formal", "country": "IN"}
    resp = _put(client, token, **chosen)
    assert resp.status_code == 200
    assert resp.json() == chosen
    assert client.get("/settings", headers={HEADER: token}).json() == chosen
    assert client.get("/settings", headers={HEADER: other}).json() == DEFAULTS


def test_settings_need_a_session(client: TestClient) -> None:
    assert client.get("/settings").status_code == 401
    assert _put(client, "not-a-session").status_code == 401


def test_settings_are_saved_only_after_consent(client: TestClient) -> None:
    token = client.post("/session", json={}).json()["session_id"]
    resp = _put(client, token, directness="direct")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "consent_required"


@pytest.mark.parametrize(
    "body",
    [
        {"directness": "blunt"},
        {"formality": "posh"},
        {"country": "XX"},  # not a country on the help card
        {"country": "in"},
        {"directness": None},
    ],
)
def test_invalid_settings_are_rejected(
    client: TestClient, start_session: Callable[..., str], body: dict[str, Any]
) -> None:
    token = start_session(client)
    resp = _put(client, token, **body)
    assert resp.status_code == 422
    assert client.get("/settings", headers={HEADER: token}).json() == DEFAULTS


def test_a_change_is_audited_by_field_name_only(
    settings: Settings, start_session: Callable[..., str]
) -> None:
    with TestClient(create_app(settings, repo=MemoryRepository())) as c:
        token = start_session(c)
        _put(c, token, directness="direct", country="GB")
        _put(c, token, directness="direct", country="GB")  # nothing changed: no entry
        export = c.get("/export", headers={HEADER: token}).json()
    entries = [a for a in export["tables"]["audit_log"] if a["event"] == "settings_changed"]
    assert [json.loads(a["detail"]) for a in entries] == [{"fields": ["country", "directness"]}]
    assert [r["country"] for r in export["tables"]["settings"]] == ["GB"]


def test_the_chosen_style_frames_the_next_reply(
    client: TestClient, start_session: Callable[..., str], llm: FakeLLM
) -> None:
    token = start_session(client)
    _chat(client, token, "work was long today")
    assert framing(StyleProfile("direct", "casual")) not in llm.last_messages[0].content
    _put(client, token, directness="direct", formality="casual")
    _chat(client, token, "work was long today")
    assert framing(StyleProfile("direct", "casual")) in llm.last_messages[0].content


def test_the_reply_carries_the_suggestion_and_the_profile_stays(
    client: TestClient, start_session: Callable[..., str]
) -> None:
    token = start_session(client)
    first = _chat(client, token, "I guess work was long").json()
    second = _chat(client, token, "maybe it's nothing").json()
    assert (first["style_suggestion"], second["style_suggestion"]) == (False, True)
    assert client.get("/settings", headers={HEADER: token}).json() == DEFAULTS


def test_a_crisis_reply_never_carries_a_suggestion(
    client: TestClient, start_session: Callable[..., str]
) -> None:
    token = start_session(client)
    _chat(client, token, "I guess work was long")
    assert _chat(client, token, "maybe I should kill myself").json()["style_suggestion"] is False


def test_deleting_the_account_removes_the_settings(
    client: TestClient, start_session: Callable[..., str]
) -> None:
    token = start_session(client)
    _put(client, token, directness="direct", country="GB")
    resp = client.request("DELETE", "/account", json={"confirm": "DELETE"},
                          headers={HEADER: token})  # fmt: skip
    assert resp.status_code == 204
    assert client.get("/settings", headers={HEADER: token}).status_code == 401


# --- pages ----------------------------------------------------------------------------------


def test_settings_page_offers_both_style_controls_with_examples(client: TestClient) -> None:
    page = client.get("/settings.html").text
    for value in ("direct", "balanced", "indirect", "casual", "neutral", "formal"):
        assert f'value="{value}"' in page
    assert page.count('type="radio"') == 6
    assert page.count('class="example"') == 6
    assert "never guesses" in page  # says the style is never inferred


def test_settings_page_lists_every_help_card_country(client: TestClient) -> None:
    page = client.get("/settings.html").text
    assert "<!-- COUNTRY OPTIONS -->" not in page
    assert '<option value="">' in page  # no country chosen: the time zone suggestion
    for country in load_resources().countries:
        assert f'<option value="{country.code}">' in page


def test_settings_page_saves_through_the_settings_endpoint(client: TestClient) -> None:
    js = client.get("/settings.js").text
    assert '"/settings"' in js
    assert '"PUT"' in js


def _app_js() -> str:
    import oasis

    return (Path(oasis.__file__).parent / "web" / "app.js").read_text(encoding="utf-8")


def test_the_help_card_opens_the_chosen_country_first() -> None:
    js = _app_js()
    assert 'api("/settings")' in js
    body = js[js.index("function suggestCountry") :]
    body = body[: body.index("\n}\n")]
    assert "chosenCountry" in body
    assert "Your chosen country:" in body
    assert "fetch" not in body  # the card itself still needs no server (rules S12)


def test_the_suggestion_is_shown_once_and_links_to_settings() -> None:
    js = _app_js()
    assert "style_suggestion" in js
    assert "settings.html" in js
    assert "styleSuggested" in js
