"""LLM client: reasoning never reaches the user, failures are typed, the queue is bounded."""

from __future__ import annotations

import functools
import json

import anyio
import httpx
import pytest
from hypothesis import given
from hypothesis import strategies as st

from oasis.llm.client import BoundedLLM, LLMFailure, clean_reply
from oasis.llm.fake import FakeLLM
from oasis.llm.llama_server import LlamaServerClient
from oasis.types import ChatMessage

MESSAGES = [ChatMessage("system", "sys"), ChatMessage("user", "hello")]


# --- clean_reply -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hello there.", "Hello there."),
        ("<think>private reasoning</think>Hello.", "Hello."),
        ("<THINK>x</THINK>  Hi", "Hi"),
        ("<think>a</think>One <think>b</think>two", "One two"),
        ("reasoning without opening tag</think>Answer", "Answer"),
        ("Visible part <think>unterminated reasoning", "Visible part"),
        ("<think \n>multi\nline</think >\nOk", "Ok"),
    ],
)
def test_clean_reply_strips_reasoning(raw: str, expected: str) -> None:
    assert clean_reply(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   \n", "<think>only reasoning</think>", "<think>unterminated", "x</think>"],
)
def test_clean_reply_rejects_empty_output(raw: str) -> None:
    with pytest.raises(LLMFailure) as info:
        clean_reply(raw)
    assert info.value.reason == "empty"


@given(st.text())
def test_clean_reply_never_returns_think_tags(raw: str) -> None:
    try:
        out = clean_reply(raw)
    except LLMFailure:
        return
    assert "<think" not in out.lower()
    assert "</think" not in out.lower()


@given(before=st.text(), reasoning=st.text(), after=st.text())
def test_reasoning_marker_never_leaks(before: str, reasoning: str, after: str) -> None:
    raw = f"{before}<think>{reasoning}SECRET-REASONING</think>{after}"
    try:
        out = clean_reply(raw)
    except LLMFailure:
        return
    assert "SECRET-REASONING" not in out


# --- FakeLLM ---------------------------------------------------------------------


@pytest.mark.anyio
async def test_fake_llm_is_deterministic() -> None:
    a = await FakeLLM().generate(MESSAGES, max_tokens=10, timeout_s=1)
    b = await FakeLLM().generate(MESSAGES, max_tokens=10, timeout_s=1)
    assert a == b
    assert a


@pytest.mark.anyio
async def test_fake_llm_cycles_scripted_replies_and_counts_calls() -> None:
    fake = FakeLLM(replies=["one", "two"])
    got = [await fake.generate(MESSAGES, max_tokens=10, timeout_s=1) for _ in range(3)]
    assert got == ["one", "two", "one"]
    assert fake.calls == 3
    assert fake.last_messages == MESSAGES


@pytest.mark.anyio
async def test_fake_llm_can_fail() -> None:
    with pytest.raises(LLMFailure) as info:
        await FakeLLM(fail="down").generate(MESSAGES, max_tokens=10, timeout_s=1)
    assert info.value.reason == "down"


# --- BoundedLLM ------------------------------------------------------------------


@pytest.mark.anyio
async def test_bounded_llm_rejects_when_queue_full() -> None:
    bounded = BoundedLLM(FakeLLM(delay_s=0.3), max_concurrency=1, queue_limit=0)
    call = functools.partial(bounded.generate, MESSAGES, max_tokens=10, timeout_s=1)
    async with anyio.create_task_group() as tg:
        tg.start_soon(call)
        await anyio.sleep(0.05)
        with pytest.raises(LLMFailure) as info:
            await call()
        assert info.value.reason == "busy"


@pytest.mark.anyio
async def test_bounded_llm_queues_within_limit() -> None:
    inner = FakeLLM(delay_s=0.05)
    bounded = BoundedLLM(inner, max_concurrency=1, queue_limit=2)
    call = functools.partial(bounded.generate, MESSAGES, max_tokens=10, timeout_s=1)
    async with anyio.create_task_group() as tg:
        for _ in range(3):
            tg.start_soon(call)
    assert inner.calls == 3


@pytest.mark.anyio
async def test_bounded_llm_releases_slot_after_failure() -> None:
    bounded = BoundedLLM(FakeLLM(fail="down"), max_concurrency=1, queue_limit=0)
    for _ in range(2):
        with pytest.raises(LLMFailure) as info:
            await bounded.generate(MESSAGES, max_tokens=10, timeout_s=1)
        assert info.value.reason == "down"
    assert await bounded.health() is True


# --- LlamaServerClient (no network: httpx.MockTransport) --------------------------


def _client(handler: httpx.MockTransport) -> LlamaServerClient:
    return LlamaServerClient(
        base_url="http://llm.test",
        model="m",
        connect_timeout_s=0.5,
        sampling={"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0},
        transport=handler,
    )


def _ok(content: str, **extra: str) -> httpx.Response:
    message = {"role": "assistant", "content": content, **extra}
    return httpx.Response(200, json={"choices": [{"message": message}]})


@pytest.mark.anyio
async def test_llama_client_sends_non_thinking_request() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return _ok("Hi.", reasoning_content="hidden chain of thought")

    client = _client(httpx.MockTransport(handler))
    reply = await client.generate(MESSAGES, max_tokens=42, timeout_s=1)
    await client.aclose()

    assert reply == "Hi."
    body = seen["body"]
    assert isinstance(body, dict)
    assert seen["path"] == "/v1/chat/completions"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["max_tokens"] == 42
    assert body["top_k"] == 20
    assert body["stream"] is False
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]


def _raises(exc: Exception) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(handler)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("transport", "reason"),
    [
        (_raises(httpx.ConnectError("refused")), "down"),
        (_raises(httpx.ReadTimeout("slow")), "timeout"),
        (_raises(httpx.RemoteProtocolError("broken")), "http_error"),
        (httpx.MockTransport(lambda r: httpx.Response(500)), "http_error"),
        (httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": []})), "bad_response"),
        (httpx.MockTransport(lambda r: httpx.Response(200, content=b"not json")), "bad_response"),
    ],
)
async def test_llama_client_maps_failures(transport: httpx.MockTransport, reason: str) -> None:
    client = _client(transport)
    with pytest.raises(LLMFailure) as info:
        await client.generate(MESSAGES, max_tokens=10, timeout_s=1)
    await client.aclose()
    assert info.value.reason == reason


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("transport", "expected"),
    [
        (httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "ok"})), True),
        (httpx.MockTransport(lambda r: httpx.Response(503)), False),
        (_raises(httpx.ConnectError("refused")), False),
    ],
)
async def test_llama_client_health(transport: httpx.MockTransport, expected: bool) -> None:
    client = _client(transport)
    assert await client.health() is expected
    await client.aclose()
