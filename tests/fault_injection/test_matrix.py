"""The full fault-injection matrix (design §16, PRD L10), one row per test, over HTTP.

Every request must end in a real or fallback reply inside the request timeout, with the
trace code the matrix names. Model failures use the real llama-server client against a
local stub server, so its timeouts and parsing are exercised, not a fake's.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import socket
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_degradation import DeadRepo, FailingRepo

from oasis.api.app import create_app
from oasis.core.engine import ChatEngine
from oasis.core.templates import TEMPLATES
from oasis.llm.fake import FakeLLM
from oasis.llm.llama_server import LlamaServerClient
from oasis.safety.handoff import HANDOFF_REPLY
from oasis.safety.rules import SafetyConfigError, load_ruleset
from oasis.settings import Settings
from oasis.types import GuardVerdict, SafetyVerdict

HEADER = "X-OASIS-Session"
TS = "2026-10-26T10:00:00Z"
GOOD = "That sounds like a lot. What has been the hardest part?"


class Stub(BaseHTTPRequestHandler):
    """A llama-server stand-in; the server's `mode` picks how it misbehaves."""

    def do_GET(self) -> None:
        self._send(200, b"{}")

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers["Content-Length"]))
        mode = self.server.mode  # type: ignore[attr-defined]
        if mode == "hang":
            time.sleep(30)
        if mode == "trickle":  # headers at once, then a byte at a time: no read ever stalls
            self.send_response(200)
            self.send_header("Content-Length", "100000")
            self.end_headers()
            with contextlib.suppress(OSError):
                for _ in range(100):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.2)
            return
        bodies = {
            "ok": _completion(GOOD),
            "empty": _completion(""),
            "think_only": _completion("<think>The user is sad, so I should</think>"),
            "bad_json": b"{not json",
            "no_choices": b'{"choices": []}',
        }
        if mode == "http_500":
            self._send(500, b"{}")
        else:
            self._send(200, bodies.get(mode, bodies["ok"]))

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with contextlib.suppress(OSError):
            self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        return None


def _completion(content: str) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": content}}]}
    ).encode()


@contextlib.contextmanager
def stub_server(mode: str) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    server.daemon_threads = True
    server.mode = mode  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _closed_port() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def _real_llm(url: str, settings: Settings) -> LlamaServerClient:
    return LlamaServerClient(
        base_url=url, model="stub", connect_timeout_s=settings.llm_connect_timeout_s, sampling={}
    )


@pytest.fixture
def traces(caplog: pytest.LogCaptureFixture) -> Callable[[], list[dict[str, Any]]]:
    caplog.set_level("INFO", logger="oasis.turn")
    return lambda: [json.loads(r.getMessage()) for r in caplog.records if r.name == "oasis.turn"]


def _turn(c: TestClient, token: str, message: str = "work has been rough this week") -> Any:
    start = time.monotonic()
    resp = c.post("/chat", json={"message": message, "client_ts": TS}, headers={HEADER: token})
    return resp, time.monotonic() - start


def _assert_answered(resp: Any, elapsed: float, settings: Settings) -> dict[str, Any]:
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    assert body["reply"].strip()
    assert elapsed < settings.request_timeout_s
    return body


# --- LLM process (real client, stub server) ------------------------------------------


@pytest.mark.parametrize(
    ("mode", "code"),
    [
        ("hang", "llm.timeout"),
        ("trickle", "llm.timeout"),
        ("empty", "llm.empty"),
        ("think_only", "llm.empty"),
        ("http_500", "llm.http_error"),
        ("bad_json", "llm.bad_response"),
        ("no_choices", "llm.bad_response"),
    ],
)
def test_llm_misbehaving_gets_the_templated_reply(
    settings: Settings, start_session: Callable[..., str], traces: Any, mode: str, code: str
) -> None:
    with (
        stub_server(mode) as url,
        TestClient(create_app(settings, llm=_real_llm(url, settings))) as c,
    ):
        resp, elapsed = _turn(c, start_session(c))
    body = _assert_answered(resp, elapsed, settings)
    assert body["templated"] is True
    assert body["reply"] == TEMPLATES["llm_unavailable"]
    assert traces()[-1]["fallback_reason"] == code
    if mode in ("hang", "trickle"):  # bounded by the generation budget, not the stub
        assert elapsed < settings.llm_generate_timeout_s + 1.5


def test_llm_down_answers_within_a_second_or_so(
    settings: Settings, start_session: Callable[..., str], traces: Any
) -> None:
    with TestClient(create_app(settings, llm=_real_llm(_closed_port(), settings))) as c:
        resp, elapsed = _turn(c, start_session(c))
    body = _assert_answered(resp, elapsed, settings)
    assert (body["templated"], traces()[-1]["fallback_reason"]) == (True, "llm.down")
    assert elapsed < settings.llm_connect_timeout_s + 1.0


def test_a_healthy_stub_gives_a_generated_reply(
    settings: Settings, start_session: Callable[..., str], traces: Any
) -> None:
    """The control row: the stub itself is not what makes the other rows fail."""
    with (
        stub_server("ok") as url,
        TestClient(create_app(settings, llm=_real_llm(url, settings))) as c,
    ):
        resp, elapsed = _turn(c, start_session(c))
    body = _assert_answered(resp, elapsed, settings)
    assert (body["reply"], body["templated"]) == (GOOD, False)
    assert traces()[-1]["fallback_reason"] is None


@pytest.mark.anyio
async def test_queue_full_gets_the_busy_reply_at_once(
    settings: Settings, start_session: Callable[..., str]
) -> None:
    one = settings.model_copy(update={"llm_max_concurrency": 1, "llm_queue_limit": 0})
    app = create_app(one, llm=FakeLLM(delay_s=1.5))
    with TestClient(app) as sync:  # runs the lifespan and opens a session
        token = start_session(sync)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            body = {"message": "work has been rough this week", "client_ts": TS}

            async def post() -> tuple[dict[str, Any], float]:
                start = time.monotonic()
                r = await c.post("/chat", json=body, headers={HEADER: token})
                return r.json(), time.monotonic() - start

            first = asyncio.create_task(post())
            await asyncio.sleep(0.3)  # the first now holds the only slot
            busy, waited = await post()
            served, _ = await first
    assert busy["reply"] == TEMPLATES["busy"]
    assert waited < 1.0  # fails fast instead of queuing behind the slow one
    assert served["templated"] is False


# --- guard -----------------------------------------------------------------------------


def _always_reject(draft: str, plan: Any) -> GuardVerdict:
    return GuardVerdict(False, ("no_advice",))


def test_guard_rejecting_twice_gets_the_vetted_fallback(
    settings: Settings,
    start_session: Callable[..., str],
    traces: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "oasis.api.app.ChatEngine", functools.partial(ChatEngine, guard=_always_reject)
    )
    llm = FakeLLM(replies=[GOOD])
    with TestClient(create_app(settings, llm=llm)) as c:
        resp, elapsed = _turn(c, start_session(c))
    body = _assert_answered(resp, elapsed, settings)
    assert body["reply"] == TEMPLATES["companion_fallback"]
    assert (llm.calls, traces()[-1]["fallback_reason"]) == (2, "guard.fallback")


def test_no_budget_for_a_retry_gets_the_vetted_fallback(
    settings: Settings,
    start_session: Callable[..., str],
    traces: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "oasis.api.app.ChatEngine", functools.partial(ChatEngine, guard=_always_reject)
    )
    tight = settings.model_copy(update={"guard_retry_min_budget_s": 60.0})
    llm = FakeLLM(replies=[GOOD])
    with TestClient(create_app(tight, llm=llm)) as c:
        resp, elapsed = _turn(c, start_session(c))
    body = _assert_answered(resp, elapsed, tight)
    assert body["reply"] == TEMPLATES["companion_fallback"]
    assert (llm.calls, traces()[-1]["fallback_reason"]) == (1, "guard.no_budget")


# --- storage ---------------------------------------------------------------------------


def test_locked_database_still_answers_and_says_it_may_not_be_saved(
    settings: Settings, start_session: Callable[..., str], tmp_path: Path
) -> None:
    on_disk = settings.model_copy(
        update={
            "storage_backend": "sqlite",
            "sqlite_busy_timeout_ms": 300,
            "request_timeout_s": 5.0,
        }
    )
    with TestClient(create_app(on_disk, llm=FakeLLM(replies=[GOOD]))) as c:
        token = start_session(c)
        other = sqlite3.connect(on_disk.db_path, isolation_level=None)
        other.execute("BEGIN EXCLUSIVE")  # another program holds the write lock
        try:
            resp, elapsed = _turn(c, token)
        finally:
            other.execute("ROLLBACK")
            other.close()
    body = _assert_answered(resp, elapsed, on_disk)
    assert body["reply"] == GOOD
    assert body["persisted"] is False
    assert "storage.busy" in body["degraded"]


def test_dead_database_still_answers(
    settings: Settings, start_session: Callable[..., str], traces: Any
) -> None:

    repo = FailingRepo()
    with TestClient(create_app(settings, llm=FakeLLM(replies=[GOOD]), repo=repo)) as c:
        token = start_session(c)
        repo.down = True
        resp, elapsed = _turn(c, token)
    body = _assert_answered(resp, elapsed, settings)
    assert (body["reply"], body["persisted"]) == (GOOD, False)
    assert "storage.down" in body["degraded"]


# --- pipeline stages -------------------------------------------------------------------


class BrokenGate:
    def check(self, text: str) -> SafetyVerdict:
        raise RuntimeError("detector bug")


def test_a_broken_safety_gate_fails_closed_to_the_handoff(
    settings: Settings, start_session: Callable[..., str]
) -> None:
    llm = FakeLLM(replies=[GOOD])
    with TestClient(create_app(settings, safety=BrokenGate(), llm=llm)) as c:
        resp, elapsed = _turn(c, start_session(c))
    body = _assert_answered(resp, elapsed, settings)
    assert (body["mode"], body["reply"], llm.calls) == ("crisis", HANDOFF_REPLY, 0)


def _boom(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("bug")


def test_explanation_error_still_answers_and_marks_the_panel(
    settings: Settings,
    start_session: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("oasis.api.app.ChatEngine", functools.partial(ChatEngine, explainer=_boom))
    with TestClient(create_app(settings, llm=FakeLLM(replies=[GOOD]))) as c:
        token = start_session(c)
        resp, elapsed = _turn(c, token)
        body = _assert_answered(resp, elapsed, settings)
        why = c.get(f"/explanations/{body['explanation_id']}", headers={HEADER: token}).json()
    assert body["reply"] == GOOD
    assert "explain.error" in body["degraded"]
    assert why["status"] == "unavailable"


def test_planner_error_gets_the_companion_template(
    settings: Settings,
    start_session: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A detector error surfaces here too: signals are computed inside the planner."""
    monkeypatch.setattr("oasis.api.app.ChatEngine", functools.partial(ChatEngine, planner=_boom))
    llm = FakeLLM(replies=[GOOD])
    with TestClient(create_app(settings, llm=llm)) as c:
        resp, elapsed = _turn(c, start_session(c))
    body = _assert_answered(resp, elapsed, settings)
    assert (body["templated"], body["mode"], llm.calls) == (True, "companion", 0)
    assert "planner.error" in body["degraded"]


def test_a_planner_error_never_hides_a_crisis(
    settings: Settings,
    start_session: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("oasis.api.app.ChatEngine", functools.partial(ChatEngine, planner=_boom))
    with TestClient(create_app(settings, llm=FakeLLM())) as c:
        resp, elapsed = _turn(c, start_session(c), "I want to kill myself")
    assert _assert_answered(resp, elapsed, settings)["reply"] == HANDOFF_REPLY


class StuckRepo(DeadRepo):
    """Storage that never answers: only the request deadline can end the turn."""

    async def get_session(self, session_hash: str) -> Any:
        await asyncio.sleep(3600)


def test_request_deadline_ends_a_stuck_turn(settings: Settings) -> None:
    fast = settings.model_copy(update={"request_timeout_s": 1.0})
    with TestClient(create_app(fast, llm=FakeLLM(), repo=StuckRepo())) as c:
        resp, elapsed = _turn(c, "any-token")
    body = _assert_answered(resp, elapsed, fast.model_copy(update={"request_timeout_s": 2.5}))
    assert (body["templated"], body["degraded"]) == (True, ["request.deadline"])
    assert body["reply"] == TEMPLATES["llm_unavailable"]


def test_a_stuck_turn_still_hands_off_a_crisis(settings: Settings) -> None:
    fast = settings.model_copy(update={"request_timeout_s": 1.0})
    with TestClient(create_app(fast, llm=FakeLLM(), repo=StuckRepo())) as c:
        resp, elapsed = _turn(c, "any-token", "I want to kill myself")
    assert _assert_answered(resp, elapsed, fast)["reply"] == HANDOFF_REPLY


@pytest.mark.anyio
async def test_crisis_bookkeeping_after_the_handoff_is_bounded(settings: Settings) -> None:
    """The audit write runs after the handoff is sent; stuck storage must not keep it forever."""
    from oasis.safety.gate import RuleBasedSafetyGate

    fast = settings.model_copy(update={"request_timeout_s": 0.5})
    engine = ChatEngine(
        safety=RuleBasedSafetyGate(load_ruleset()), llm=FakeLLM(), repo=StuckRepo(), settings=fast
    )
    verdict = SafetyVerdict(is_crisis=True, tiers=frozenset({"explicit"}), pattern_ids=("x",))
    await asyncio.wait_for(engine.record_crisis("h", verdict), timeout=3.0)


def test_invalid_safety_content_refuses_to_start() -> None:
    with pytest.raises(SafetyConfigError):
        load_ruleset("schema: oasis.content/v1\nkind: safety_patterns\npatterns: []\n")


# --- combined faults -------------------------------------------------------------------


def test_everything_down_at_once_still_answers_and_hands_off(settings: Settings) -> None:
    with (
        stub_server("hang") as url,
        TestClient(create_app(settings, llm=_real_llm(url, settings), repo=DeadRepo())) as c,
    ):
        crisis, crisis_s = _turn(c, "unknown-session", "I don't want to live anymore")
        ordinary, ordinary_s = _turn(c, "unknown-session")
    assert _assert_answered(crisis, crisis_s, settings)["reply"] == HANDOFF_REPLY
    assert crisis_s < 1.0  # the handoff never waits for the model or the database
    # Consent cannot be checked, so an ordinary message is refused at once, not left hanging.
    assert ordinary.status_code == 403
    assert ordinary_s < settings.request_timeout_s


def test_slow_model_and_locked_database_together(
    settings: Settings, start_session: Callable[..., str], traces: Any
) -> None:
    on_disk = settings.model_copy(
        update={"storage_backend": "sqlite", "sqlite_busy_timeout_ms": 300}
    )
    with (
        stub_server("hang") as url,
        TestClient(create_app(on_disk, llm=_real_llm(url, on_disk))) as c,
    ):
        token = start_session(c)
        other = sqlite3.connect(on_disk.db_path, isolation_level=None)
        other.execute("BEGIN EXCLUSIVE")
        try:
            resp, elapsed = _turn(c, token)
        finally:
            other.execute("ROLLBACK")
            other.close()
    body = _assert_answered(resp, elapsed, on_disk)
    assert (body["templated"], body["persisted"]) == (True, False)
    assert traces()[-1]["fallback_reason"] == "llm.timeout"
