"""Load test and latency profile on the reference laptop (Phase 13, PRD L7 and §6.1). NOT run
in CI. Every request goes over HTTP through the whole app (one process, as `uvicorn` runs it),
with a fresh SQLite file per run.

    uv run python scripts/load_test.py profile   # everything except the model (fake model)
    uv run python scripts/load_test.py load      # concurrent sessions against llama-server
    uv run python scripts/load_test.py stream    # what sentence-by-sentence streaming would gain

`load` and `stream` need llama-server running (see scripts/model_smoke_test.py); `--url`
overrides OASIS_LLM_URL. `--out FILE` writes the markdown as well as printing it.

- profile: 20 sessions x 30 messages, one at a time; p50/p95/p99 per request against the
  150 ms p95 target for everything except the model.
- load: N sessions at once (N from `--levels`), each sending `--turns` messages one after
  another, the way people type. A request is served when it gets the model's reply, or a
  guard fallback, inside the request timeout; busy and timeout replies are not. The
  concurrency limit reported is the largest N with every request served. RAM: llama-server's
  peak resident and committed memory, this process's (the app's) peak, and the lowest free
  system RAM during the level.
- stream: the same pipeline with the model asked to stream; records when the first sentence
  arrived against the whole reply, and how often the guard rejected a first draft, which is
  text sentence streaming would already have shown.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import pathlib
import re
import runpy
import statistics
import sys
import tempfile
import time
from collections.abc import Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
import psutil

from oasis.api.app import create_app
from oasis.api.pages import load_disclosure
from oasis.llm.client import LLMFailure
from oasis.llm.fake import FakeLLM
from oasis.llm.llama_server import LlamaServerClient
from oasis.settings import Settings
from oasis.types import ChatMessage

HEADER = "X-OASIS-Session"
TS = "2026-10-26T10:00:00Z"
MESSAGES: list[str] = runpy.run_path(str(pathlib.Path(__file__).with_name("tone_check.py")))[
    "SINGLES"
]
NOT_SERVED = {"llm.busy", "llm.timeout", "request.deadline"}
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


@dataclass
class Result:
    seconds: float
    reason: str | None  # fallback reason from the trace, or the route's degraded code
    first_pass: bool | None


class Traces(logging.Handler):
    """Collects each turn's trace by turn ID (IDs and codes only, never text)."""

    def __init__(self) -> None:
        super().__init__()
        self.by_turn: dict[str, dict[str, Any]] = {}

    def emit(self, record: logging.LogRecord) -> None:
        trace = json.loads(record.getMessage())
        self.by_turn[trace["turn_id"]] = trace


def pct(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def ms(values: Sequence[float]) -> str:
    return " / ".join(f"{pct(values, q) * 1000:.0f}" for q in (0.5, 0.95, 0.99))


def secs(values: Sequence[float]) -> str:
    return " / ".join(f"{pct(values, q):.1f}" for q in (0.5, 0.95))


@asynccontextmanager
async def client(settings: Settings, llm: Any) -> Any:
    app = create_app(settings, llm=llm)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://oasis") as c:
            yield c


async def session(c: httpx.AsyncClient) -> str:
    token: str = (await c.post("/session", json={"ephemeral": False})).json()["session_id"]
    version = load_disclosure().version
    await c.post("/consent", json={"disclosure_version": version}, headers={HEADER: token})
    return token


async def send(c: httpx.AsyncClient, token: str, message: str, traces: Traces) -> Result:
    start = time.perf_counter()
    resp = await c.post(
        "/chat", json={"message": message, "client_ts": TS}, headers={HEADER: token}, timeout=None
    )
    seconds = time.perf_counter() - start
    body = resp.json()
    trace = traces.by_turn.get(body["turn_id"], {})
    reason = trace.get("fallback_reason") or next(iter(body["degraded"]), None)
    outcomes = trace.get("guard_outcomes") or []
    return Result(seconds, reason, outcomes[0] == "pass" if outcomes else None)


def settings_for(args: argparse.Namespace, db: pathlib.Path) -> Settings:
    s = Settings(storage_backend="sqlite", db_path=db)
    return s.model_copy(update={"llm_url": args.url}) if args.url else s


def machine() -> str:
    mem = psutil.virtual_memory().total / 2**30
    return (
        f"{psutil.cpu_count(logical=False)} cores / {psutil.cpu_count()} threads, {mem:.1f} GB RAM"
    )


async def profile(args: argparse.Namespace, traces: Traces, db: pathlib.Path) -> list[str]:
    times: list[float] = []
    async with client(settings_for(args, db), FakeLLM()) as c:
        await send(c, await session(c), MESSAGES[0], traces)  # warm-up, not counted
        for _ in range(20):
            token = await session(c)
            for message in MESSAGES[:30]:
                times.append((await send(c, token, message, traces)).seconds)
    stages: dict[str, list[float]] = {}
    for trace in traces.by_turn.values():
        for stage in trace["stages"]:
            stages.setdefault(stage["name"], []).append(stage["duration_ms"] / 1000)
    return [
        "## Everything except the model (fake model)",
        "",
        f"{len(times)} requests over HTTP, one at a time, SQLite on disk; {machine()}.",
        "",
        "| Measure | p50 / p95 / p99 (ms) |",
        "|---|---|",
        f"| Whole request | {ms(times)} |",
        *(f"| Stage: {name} | {ms(v)} |" for name, v in stages.items()),
        "",
        f"Target: < 150 ms p95. **{'Met' if pct(times, 0.95) < 0.150 else 'Not met'}.**",
    ]


class RSS:
    """Peak memory of llama-server and of this process while a level runs: resident (in RAM
    now) and committed (on Windows, private bytes, which count pages moved to disk)."""

    def __init__(self) -> None:
        self.model = 0
        self.model_committed = 0
        self.app = 0
        self.free = psutil.virtual_memory().available
        servers = [p for p in psutil.process_iter(["name"]) if "llama-server" in (p.name() or "")]
        self._server = servers[0] if servers else None
        self._me = psutil.Process()

    async def watch(self) -> None:
        while True:
            self.app = max(self.app, self._me.memory_info().rss)
            self.free = min(self.free, psutil.virtual_memory().available)
            if self._server is not None:
                mem = self._server.memory_info()
                self.model = max(self.model, mem.rss)
                committed = getattr(mem, "private", mem.rss)
                self.model_committed = max(self.model_committed, committed)
            await asyncio.sleep(0.5)


async def load(args: argparse.Namespace, traces: Traces, db: pathlib.Path) -> list[str]:
    s = settings_for(args, db)
    lines = [
        "## Concurrent sessions (real model)",
        "",
        f"Model {s.llm_model} at {s.llm_url}; {machine()}. One generation at a time "
        f"(`llm_max_concurrency` {s.llm_max_concurrency}), {s.llm_queue_limit} waiting at most, "
        f"request timeout {s.request_timeout_s:.0f} s. Each session sends {args.turns} messages "
        "one after another.",
        "",
        "| Sessions at once | Requests | Served | Busy | Timed out | Guard fallback "
        "| Latency p50 / p95 (s) | Slowest (s) | llama-server in RAM / committed (GB) "
        "| App RAM (MB) | System RAM free, lowest (GB) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    limit = 0
    async with client(s, LlamaServerClient.from_settings(s)) as c:
        await send(c, await session(c), MESSAGES[0], traces)  # load the model, not counted
        for n in args.levels:
            rss = RSS()
            watcher = asyncio.create_task(rss.watch())

            async def one(i: int) -> list[Result]:
                token = await session(c)
                picks = [MESSAGES[(i * args.turns + k) % len(MESSAGES)] for k in range(args.turns)]
                return [await send(c, token, m, traces) for m in picks]

            results = [r for rs in await asyncio.gather(*(one(i) for i in range(n))) for r in rs]
            watcher.cancel()
            served = [r for r in results if r.reason not in NOT_SERVED]
            busy = sum(r.reason == "llm.busy" for r in results)
            late = sum(r.reason in ("llm.timeout", "request.deadline") for r in results)
            guard = sum((r.reason or "").startswith("guard.") for r in results)
            if len(served) == len(results):
                limit = n
            t = [r.seconds for r in results]
            lines.append(
                f"| {n} | {len(results)} | {len(served)} | {busy} | {late} | {guard} | {secs(t)} "
                f"| {max(t):.1f} | {rss.model / 2**30:.2f} / {rss.model_committed / 2**30:.2f} "
                f"| {rss.app / 2**20:.0f} | {rss.free / 2**30:.2f} |"
            )
            print(lines[-1], flush=True)
    lines += ["", f"**Largest number of sessions at once with every request served: {limit}.**"]
    return lines


class StreamingProbe:
    """Asks llama-server to stream and times the first token, the first sentence and the
    whole reply. The full text still goes to the guard, as without streaming."""

    def __init__(self, s: Settings) -> None:
        self._s = s
        self._http = httpx.AsyncClient(base_url=s.llm_url)
        self.timings: list[tuple[float, float, float]] = []  # first token, sentence, all

    async def generate(
        self, messages: Sequence[ChatMessage], *, max_tokens: int, timeout_s: float
    ) -> str:
        s = self._s
        payload = {
            "model": s.llm_model, "max_tokens": max_tokens, "stream": True,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "chat_template_kwargs": {"enable_thinking": False},
            "temperature": s.llm_temperature, "top_p": s.llm_top_p, "top_k": s.llm_top_k,
            "min_p": s.llm_min_p,
        }  # fmt: skip
        start = time.perf_counter()
        first = sentence = 0.0
        text = ""
        try:
            async with self._http.stream(
                "POST", "/v1/chat/completions", json=payload, timeout=timeout_s
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    delta = json.loads(line[6:])["choices"][0]["delta"].get("content") or ""
                    if delta and not first:
                        first = time.perf_counter() - start
                    text += delta
                    if not sentence and _SENTENCE_END.search(text):
                        sentence = time.perf_counter() - start
        except httpx.HTTPError:
            raise LLMFailure("timeout") from None
        total = time.perf_counter() - start
        self.timings.append((first, sentence or total, total))
        return text

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        await self._http.aclose()


async def stream(args: argparse.Namespace, traces: Traces, db: pathlib.Path) -> list[str]:
    s = settings_for(args, db)
    probe = StreamingProbe(s)
    results: list[Result] = []
    async with client(s, probe) as c:
        await send(c, await session(c), MESSAGES[0], traces)  # warm-up
        probe.timings.clear()
        for message in MESSAGES[: args.messages]:
            results.append(await send(c, await session(c), message, traces))
    first, sentence, total = (list(x) for x in zip(*probe.timings, strict=True))
    drafted = [r.first_pass for r in results if r.first_pass is not None]
    rejected = sum(not p for p in drafted)
    gain = statistics.median(t - f for f, t in zip(sentence, total, strict=True))
    return [
        "## Sentence streaming (measured, not built)",
        "",
        f"{len(results)} single messages through the full pipeline, model streaming; "
        f"{len(probe.timings)} generations (retries included).",
        "",
        "| Measure | p50 / p95 (s) |",
        "|---|---|",
        f"| First token | {secs(first)} |",
        f"| First sentence complete | {secs(sentence)} |",
        f"| Whole reply (what the user waits for today) | {secs(total)} |",
        "",
        f"Median time a first sentence would appear sooner: {gain:.1f} s.",
        f"First drafts the guard rejected: {rejected}/{len(drafted)}. With sentence streaming "
        "these would already be on screen before the guard saw the whole draft.",
    ]


async def main(args: argparse.Namespace) -> list[str]:
    traces = Traces()
    log = logging.getLogger("oasis.turn")
    log.addHandler(traces)
    log.setLevel(logging.INFO)
    log.propagate = False
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "load.db"
        run = {"profile": profile, "load": load, "stream": stream}[args.mode]
        return await run(args, traces, db)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("mode", choices=["profile", "load", "stream"])
    parser.add_argument("--url", help="llama-server URL (default: OASIS_LLM_URL)")
    parser.add_argument(
        "--levels",
        type=lambda v: [int(x) for x in v.split(",")],
        default=[1, 2, 3, 4, 6, 8],
        help="sessions at once, e.g. 1,2,4",
    )
    parser.add_argument("--turns", type=int, default=3, help="messages per session (load)")
    parser.add_argument("--messages", type=int, default=20, help="messages (stream)")
    parser.add_argument("--out", type=pathlib.Path, help="also write the markdown here")
    args = parser.parse_args()
    lines = asyncio.run(main(args))
    print(*lines, sep="\n")
    if args.out:
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.exit(0)
