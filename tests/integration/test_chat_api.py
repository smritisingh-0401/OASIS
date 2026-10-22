"""HTTP contract for the endpoints (design §12) and the security envelope (rules P3, P6, F1)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import oasis
from oasis.api.app import create_app
from oasis.llm.fake import FakeLLM
from oasis.psychoed.selector import load_all as load_psychoed
from oasis.router.exercise import technique_for
from oasis.router.weights import config as router_config
from oasis.safety.handoff import HANDOFF_REPLY
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.types import ChatMessage, SafetyVerdict

HEADER = "X-OASIS-Session"
TS = "2026-10-07T10:00:00+05:30"


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(
        create_app(settings, llm=FakeLLM(replies=["That sounds like a lot. What's on your mind?"]))
    ) as c:
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
        assert body["reply"] == "That sounds like a lot. What's on your mind?"
        assert body["mode"] == "companion"
        assert body["persisted"] is True

    history = client.get("/history", headers={HEADER: token}).json()["turns"]
    assert [(t["role"], t["content"]) for t in history] == [
        ("user", "first"),
        ("assistant", "That sounds like a lot. What's on your mind?"),
        ("user", "second"),
        ("assistant", "That sounds like a lot. What's on your mind?"),
    ]


def test_history_limit(client: TestClient) -> None:
    token = _session(client)
    _chat(client, token, "a")
    _chat(client, token, "b")
    turns = client.get("/history?limit=1", headers={HEADER: token}).json()["turns"]
    assert [t["content"] for t in turns] == ["That sounds like a lot. What's on your mind?"]


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


def test_chat_page_has_help_card_and_disclaimer(client: TestClient) -> None:
    html = client.get("/").text
    assert "Need help now?" in html
    assert "not a diagnosis" in html
    # Owner's wording (2026-10-12, CR-03): an invitation to talk in person, not an
    # emergency instruction, at the top of the card.
    assert "<h2>Talk to someone now</h2>" in html
    assert "If you feel like talking to someone in person" in html
    assert "If you are in danger right now" not in html


def test_crisis_reply_invites_talking_in_person_and_points_to_the_card() -> None:
    assert "If you feel like talking to someone in person" in HANDOFF_REPLY
    assert '"Need help now?"' in HANDOFF_REPLY
    assert "emergency" not in HANDOFF_REPLY


def test_help_card_lists_crisis_lines_without_external_loads(client: TestClient) -> None:
    html = client.get("/").text
    assert "<!-- CRISIS_RESOURCES -->" not in html
    assert "Tele-MANAS" in html
    assert 'href="tel:14416"' in html
    # Crisis-line websites are user-initiated links; nothing is loaded from elsewhere.
    assert not re.search(r"""\bsrc=["']?(https?:)?//""", html, re.I)


def test_web_assets_make_no_external_requests() -> None:
    web = Path(oasis.__file__).parent / "web"
    # What the browser parses; the font is binary and its licence text is never loaded.
    files = [p for p in web.rglob("*") if p.suffix in {".html", ".css", ".js"}]
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


def test_history_survives_restart(settings: Settings) -> None:
    on_disk = settings.model_copy(update={"storage_backend": "sqlite"})
    with TestClient(
        create_app(on_disk, llm=FakeLLM(replies=["That sounds nice. What else happened?"]))
    ) as c:
        token = _session(c)
        _chat(c, token, "remember me")

    with TestClient(create_app(on_disk)) as c:
        turns = c.get("/history", headers={HEADER: token}).json()["turns"]
    assert [t["content"] for t in turns] == ["remember me", "That sounds nice. What else happened?"]


def test_default_llm_backend_is_llama_server(settings: Settings) -> None:
    app = create_app(
        settings.model_copy(update={"llm_backend": "llama_server", "llm_url": "http://127.0.0.1:9"})
    )
    with TestClient(app) as c:
        assert c.get("/health").json()["llm"] == "down"
        resp = _chat(c, _session(c))
    assert resp.json()["templated"] is True


# --- crisis flow through the real gate (design §2.4) ------------------------------


CRISIS = "I want to kill myself"


def test_crisis_writes_audit_and_holds_post_crisis_mode(settings: Settings) -> None:
    repo = MemoryRepository()
    llm = FakeLLM(replies=["That sounds like a lot. What's on your mind?"])
    with TestClient(create_app(settings, llm=llm, repo=repo)) as c:
        token = _session(c)
        crisis = _chat(c, token, CRISIS).json()
        held = _chat(c, token, "hello").json()
        cleared = _chat(c, token, "I'd like to keep talking.").json()
        turns = c.get("/history", headers={HEADER: token}).json()["turns"]

    assert crisis["mode"] == "crisis"
    assert crisis["reply"] == HANDOFF_REPLY
    assert crisis["persisted"] is False
    assert held["mode"] == "post_crisis"
    assert cleared["mode"] == "companion"
    assert llm.calls == 1  # only the turn after the user chose to continue

    # The crisis message itself is never stored; a placeholder stands in for it.
    assert CRISIS not in json.dumps(turns)
    assert turns[0]["role"] == "placeholder"
    assert turns[0]["mode"] == "crisis"

    user_id = next(iter(repo._sessions.values()))
    [audit] = repo._audit[user_id]
    assert audit.event == "crisis_handoff"
    detail = json.loads(audit.detail)
    assert detail["tiers"] == ["explicit"]
    assert detail["source"] == "text"
    assert detail["pattern_ids"] == ["explicit.kill_self"]
    assert CRISIS not in audit.detail


# --- assessment through HTTP (design §4, §12) -------------------------------------------


def _act(client: TestClient, token: str, label: str, action: dict[str, Any]) -> Any:
    body = {"message": label, "client_ts": TS, "action": action}
    resp = client.post("/chat", json=body, headers={HEADER: token})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _start_phq9(client: TestClient, token: str) -> None:
    offer = _chat(client, token, "can I take a depression test?").json()
    assert offer["mode"] == "assessment"
    assert offer["assessment"]["step"] == "offer"
    first = _act(client, token, "Yes", {"type": "assessment_consent", "accept": True})
    assert (first["assessment"]["step"], first["assessment"]["item"]) == ("item", 1)


def test_instruction_is_its_own_message_before_the_first_question(settings: Settings) -> None:
    with TestClient(create_app(settings, repo=MemoryRepository())) as c:
        token = _session(c)
        _chat(c, token, "can I take a depression test?")
        first = _act(c, token, "Yes", {"type": "assessment_consent", "accept": True})
        turns = c.get("/history", headers={HEADER: token}).json()["turns"]
    stem = (
        "Over the last 2 weeks, how often have you been bothered by any of the following problems?"
    )
    assert first["preface"] == stem
    assert first["reply"].startswith("Question 1 of 9: ")
    # Stored as two assistant turns, so a reload shows two bubbles in the same order.
    assert [t["content"] for t in turns[-2:]] == [stem, first["reply"]]
    assert {t["role"] for t in turns[-2:]} == {"assistant"}


def test_history_restores_the_open_assessment_card(settings: Settings) -> None:
    def card(c: TestClient, token: str) -> Any:
        return c.get("/history", headers={HEADER: token}).json()["assessment"]

    with TestClient(create_app(settings, repo=MemoryRepository())) as c:
        token = _session(c)
        assert card(c, token) is None
        _chat(c, token, "can I take a depression test?")
        assert card(c, token)["step"] == "offer"
        _act(c, token, "Yes", {"type": "assessment_consent", "accept": True})
        answer = {"type": "assessment_answer", "value": 0, "instrument": "PHQ9", "item": 1}
        _act(c, token, "Not at all", answer)
        restored = card(c, token)
        assert (restored["step"], restored["item"], restored["item_count"]) == ("item", 2, 9)
        assert restored["options"][0] == "Not at all"
        _act(c, token, "Pause", {"type": "assessment_pause"})
        assert (card(c, token)["step"], card(c, token)["item"]) == ("paused", 2)
        _act(c, token, "Stop", {"type": "assessment_abort"})
        assert card(c, token) is None


def test_full_phq9_over_http(settings: Settings) -> None:
    repo = MemoryRepository()
    with TestClient(create_app(settings, repo=repo)) as c:
        token = _session(c)
        _start_phq9(c, token)
        for item, value in enumerate([1, 1, 1, 1, 1, 0, 0, 0, 0], start=1):
            body = _act(c, token, "Several days", {"type": "assessment_answer", "value": value,
                                                   "instrument": "PHQ9", "item": item})  # fmt: skip
        assert body["assessment"]["step"] == "functional"
        functional = {"type": "assessment_answer", "value": 1, "instrument": "PHQ9", "item": None}
        result = _act(c, token, "Somewhat difficult", functional)
        turns = c.get("/history", headers={HEADER: token}).json()["turns"]
    card = result["assessment"]
    assert (card["step"], card["total"], card["band"]) == ("result", 5, "mild")
    assert "not a diagnosis" in result["reply"]
    assert result["templated"] is True
    [rec] = next(iter(repo._assessments.values()))
    assert (rec.status, rec.total, rec.functional) == ("scored", 5, 1)
    assert any(t["content"] == "Somewhat difficult" for t in turns)


def test_item9_over_http_hands_off_and_audits_the_source(settings: Settings) -> None:
    repo = MemoryRepository()
    with TestClient(create_app(settings, repo=repo)) as c:
        token = _session(c)
        _start_phq9(c, token)
        for item in range(1, 9):
            _act(c, token, "Not at all", {"type": "assessment_answer", "value": 0,
                                          "instrument": "PHQ9", "item": item})  # fmt: skip
        crisis = _act(c, token, "Several days", {"type": "assessment_answer", "value": 1,
                                                 "instrument": "PHQ9", "item": 9})  # fmt: skip
        held = _chat(c, token, "ok").json()
    assert crisis["mode"] == "crisis"
    assert crisis["reply"] == HANDOFF_REPLY
    assert crisis["assessment"] is None
    assert held["mode"] == "post_crisis"
    user_id = next(iter(repo._sessions.values()))
    [audit] = repo._audit[user_id]
    assert json.loads(audit.detail)["source"] == "item9"
    [rec] = repo._assessments[user_id]
    assert (rec.status, rec.total) == ("escalated", None)


@pytest.mark.parametrize(
    "action",
    [
        {"type": "assessment_answer", "value": 4, "instrument": "PHQ9", "item": 1},
        {"type": "assessment_answer", "value": 1, "instrument": "PHQ9", "item": 0},
        {"type": "assessment_answer", "value": 1, "instrument": "BDI", "item": 1},
        {"type": "assessment_dance"},
    ],
)
def test_invalid_actions_get_typed_422(client: TestClient, action: dict[str, Any]) -> None:
    token = _session(client)
    resp = client.post(
        "/chat", json={"message": "x", "client_ts": TS, "action": action}, headers={HEADER: token}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_turn"


# --- therapy router over HTTP (Phase 4) ----------------------------------------------

DISTORTED = "I'm such a failure, I always mess everything up"


def test_structured_mode_offer_consent_steps_and_stop_over_http(settings: Settings) -> None:
    with TestClient(create_app(settings, repo=MemoryRepository())) as c:
        token = _session(c)
        for _ in range(router_config().hysteresis_turns - 1):
            assert _chat(c, token, DISTORTED).json()["exercise"] is None
        offer = _chat(c, token, DISTORTED).json()
        assert offer["exercise"]["step"] == "offer"
        assert offer["exercise"]["mode"] == "cbt"
        restored = c.get("/history", headers={HEADER: token}).json()["exercise"]
        assert restored["step"] == "offer"

        first = _act(c, token, "Yes, let's try", {"type": "exercise_consent", "accept": True})
        assert first["mode"] == "cbt"
        assert (first["exercise"]["step"], first["exercise"]["item"]) == ("active", 1)
        assert first["exercise"]["instruction"] == technique_for("cbt").steps[0]
        second = _chat(c, token, "It's the thought that I always get things wrong").json()
        assert second["exercise"]["item"] == 2
        assert c.get("/history", headers={HEADER: token}).json()["exercise"]["item"] == 2

        stopped = _act(c, token, "Stop", {"type": "exercise_stop"})
        assert stopped["exercise"] is None
        assert c.get("/history", headers={HEADER: token}).json()["exercise"] is None


def test_acute_overwhelm_starts_grounding_over_http(settings: Settings) -> None:
    with TestClient(create_app(settings, repo=MemoryRepository())) as c:
        token = _session(c)
        body = _chat(c, token, "I can't breathe, everything is too much, I'm falling apart").json()
    assert body["mode"] == "grounding"
    assert body["exercise"]["step"] == "active"
    assert body["exercise"]["mode"] == "grounding"


def test_declining_a_structured_mode_over_http(settings: Settings) -> None:
    with TestClient(create_app(settings, repo=MemoryRepository())) as c:
        token = _session(c)
        for _ in range(3):
            _chat(c, token, DISTORTED)
        body = _act(c, token, "Not now", {"type": "exercise_consent", "accept": False})
    assert body["exercise"] is None
    assert body["mode"] == "companion"


@pytest.mark.parametrize("action", [
    {"type": "exercise_consent"},
    {"type": "exercise_consent", "accept": True, "mode": "cbt"},
    {"type": "exercise_stop", "extra": 1},
    {"type": "exercise_jump"},
])  # fmt: skip
def test_malformed_exercise_actions_are_rejected(
    settings: Settings, action: dict[str, Any]
) -> None:
    with TestClient(create_app(settings, repo=MemoryRepository())) as c:
        token = _session(c)
        resp = c.post("/chat", json={"message": "Yes", "client_ts": TS, "action": action},
                      headers={HEADER: token})  # fmt: skip
    assert resp.status_code == 422


# --- psychoeducation over HTTP (Phase 5) ---------------------------------------------


def test_psychoeducation_over_http(settings: Settings) -> None:
    general = next(i for i in load_psychoed() if i.id == "general")
    with TestClient(create_app(settings, repo=MemoryRepository())) as c:
        token = _session(c)
        body = _chat(c, token, "what's wrong with me?").json()
        assert (body["mode"], body["reply"]) == ("psychoed", general.text)
        combined = _chat(c, token, "is something wrong with me? can I do a depression test").json()
    assert combined["mode"] == "assessment"
    assert combined["preface"]
    assert combined["assessment"]["step"] == "offer"


# --- mood trend (Phase 8, FR-TRK-3) ----------------------------------------------------------

LABEL = "language-based mood trend, not a clinical measure"


def test_trends_over_http(client: TestClient) -> None:
    token = _session(client)
    _chat(client, token, "I always feel so tired")
    _chat(client, token, "a bit better now")
    body = client.get("/trends", headers={HEADER: token}).json()
    assert body["label"] == LABEL
    assert len(body["current"]) == 2
    assert len(body["sessions"]) == len(body["ewma"]) == 1
    assert body["change_flags"] == [False]
    info = {f["name"]: f for f in body["features"]}
    assert info["valence"]["source"]
    assert info["fp_pronoun_rate"]["source"]
    assert info["msg_length"]["exploratory"] is True


def test_trends_need_a_session(client: TestClient) -> None:
    assert client.get("/trends").status_code == 401
    assert client.get("/trends", headers={HEADER: "not-a-session"}).status_code == 401


def test_the_trend_page_always_shows_the_label(client: TestClient) -> None:
    page = client.get("/trends.html")
    assert page.status_code == 200
    assert LABEL in page.text
    assert 'src="trends.js"' in page.text
    assert client.get("/trends.js").status_code == 200
    assert 'href="trends.html"' in client.get("/").text


def test_memory_storage_writes_nothing_to_disk(settings: Settings, tmp_path: Path) -> None:
    with TestClient(create_app(settings, llm=FakeLLM())) as c:
        token = _session(c)
        _chat(c, token, "I always feel so tired")
        assert c.get("/trends", headers={HEADER: token}).status_code == 200
    assert list(tmp_path.iterdir()) == []


# --- explanations (Phase 9) -----------------------------------------------------------------


def test_every_reply_links_to_its_explanation(client: TestClient) -> None:
    token = _session(client)
    reply = _chat(client, token, "I always mess everything up").json()
    assert reply["explanation_id"] == reply["turn_id"]
    resp = client.get(f"/explanations/{reply['explanation_id']}", headers={HEADER: token})
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    body = resp.json()
    assert body["status"] == "ok"
    assert "exact wording" in body["scope_note"]
    assert body["plain_language"]


def test_history_marks_explained_replies(client: TestClient) -> None:
    token = _session(client)
    reply = _chat(client, token, "hello").json()
    turns = client.get("/history", headers={HEADER: token}).json()["turns"]
    assert [(t["role"], t["explanation_id"]) for t in turns] == [
        ("user", None),
        ("assistant", reply["turn_id"]),
    ]


def test_explanations_are_scoped_to_the_session_user(client: TestClient) -> None:
    owner, other = _session(client), _session(client)
    eid = _chat(client, owner, "hello").json()["explanation_id"]
    assert client.get(f"/explanations/{eid}", headers={HEADER: other}).status_code == 404
    assert client.get(f"/explanations/{eid}").status_code == 401
    assert client.get("/explanations/" + "0" * 32, headers={HEADER: owner}).status_code == 404
    assert client.get("/explanations/not-an-id", headers={HEADER: owner}).status_code == 404


def test_crisis_reply_carries_no_explanation(client: TestClient) -> None:
    token = _session(client)
    body = _chat(client, token, "I want to kill myself").json()
    assert body["mode"] == "crisis"
    assert body["explanation_id"] is None


def test_the_why_panel_is_fetched_on_demand() -> None:
    js = (Path(oasis.__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
    assert "/explanations/" in js
    assert "Why this reply?" in js
    assert "See details" in js
    assert "Explanation unavailable for this reply." in js
