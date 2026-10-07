"""Model bake-off: RAM, first-token time and tokens/sec per model. NOT run in CI.

Launches llama-server once per model, warms it up, then streams a fixed prompt set.

Usage (one --model per candidate, NAME=PATH):
    uv run python scripts/model_bakeoff.py --server-bin C:/llama.cpp/llama-server.exe \
        --model qwen3.5-4b=models/Qwen3.5-4B-Q4_K_M.gguf \
        --model gemma4-e4b=models/gemma-4-E4B-it-Q4_K_M.gguf \
        --model phi4-mini=models/Phi-4-mini-instruct-Q4_K_M.gguf \
        --out docs/reports/bakeoff.json

Record the llama.cpp build (`llama-server --version`) with the results: the hybrid
architecture of Qwen3.5 needs a recent build, and the build is pinned from these runs.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import psutil

from oasis.llm.prompt import build_messages
from oasis.types import Plan

PROMPTS = [
    "I've had a really long week and I feel worn out.",
    "My friend didn't reply to my message and now I feel like nobody cares.",
    "I keep thinking I'll fail my exam even though I studied.",
    "I just want to talk for a bit.",
    "Work has been overwhelming and I can't switch off at night.",
]


def wait_healthy(url: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/health", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise TimeoutError("llama-server did not become healthy")


def stream_once(url: str, prompt: str, max_tokens: int) -> dict[str, float]:
    plan = Plan(mode="companion", constraints=("one_question",))
    payload = {
        "messages": [
            {"role": m.role, "content": m.content}
            for m in build_messages(plan, [], prompt, history_turns=0)
        ],
        "max_tokens": max_tokens,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
    }
    start = time.perf_counter()
    first_token: float | None = None
    timings: dict[str, Any] = {}
    with httpx.stream("POST", f"{url}/v1/chat/completions", json=payload, timeout=120) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            delta = (chunk.get("choices") or [{}])[0].get("delta", {})
            if first_token is None and delta.get("content"):
                first_token = time.perf_counter() - start
            timings = chunk.get("timings", timings)
    return {
        "first_token_s": first_token if first_token is not None else float("nan"),
        "total_s": time.perf_counter() - start,
        "tokens_per_s": float(timings.get("predicted_per_second", float("nan"))),
        "prompt_tokens": float(timings.get("prompt_n", float("nan"))),
    }


def bench_model(args: argparse.Namespace, name: str, model_path: str) -> dict[str, Any]:
    url = f"http://127.0.0.1:{args.port}"
    cmd = [
        args.server_bin,
        "-m",
        model_path,
        "--jinja",
        "-c",
        str(args.ctx),
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
    ]
    if args.threads:
        cmd += ["-t", str(args.threads)]
    print(f"\n--- {name}: {' '.join(cmd)}", flush=True)
    server = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_healthy(url, args.load_timeout)
        proc = psutil.Process(server.pid)
        stream_once(url, "Hello.", 16)  # warm-up, not measured
        runs = [stream_once(url, p, args.max_tokens) for _ in range(args.runs) for p in PROMPTS]
        rss_mb = proc.memory_info().rss / 2**20
    finally:
        server.terminate()
        server.wait(timeout=30)

    def med(key: str) -> float:
        return statistics.median(r[key] for r in runs)

    def p95(key: str) -> float:
        return statistics.quantiles([r[key] for r in runs], n=20, method="inclusive")[18]

    return {
        "model": name,
        "path": model_path,
        "runs": len(runs),
        "rss_mb": round(rss_mb, 1),
        "first_token_s_median": round(med("first_token_s"), 3),
        "first_token_s_p95": round(p95("first_token_s"), 3),
        "total_s_median": round(med("total_s"), 3),
        "tokens_per_s_median": round(med("tokens_per_s"), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--server-bin", required=True)
    parser.add_argument("--model", action="append", required=True, metavar="NAME=PATH")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--ctx", type=int, default=4096)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--runs", type=int, default=3, help="passes over the prompt set")
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--load-timeout", type=float, default=300)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    results = []
    for spec in args.model:
        name, _, path = spec.partition("=")
        results.append(bench_model(args, name, path))

    header = f"{'model':<16}{'RSS MB':>9}{'TTFT med':>10}{'TTFT p95':>10}{'tok/s':>8}"
    print("\n" + header)
    for r in results:
        print(
            f"{r['model']:<16}{r['rss_mb']:>9}{r['first_token_s_median']:>10}"
            f"{r['first_token_s_p95']:>10}{r['tokens_per_s_median']:>8}"
        )
    if args.out:
        args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nSaved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
