"""Real-model smoke test against a running llama-server. NOT run in CI (needs model weights).

Start the server first, for example:
    llama-server -m models/Qwen3.5-4B-Q4_K_M.gguf --jinja -c 4096 --host 127.0.0.1 --port 8080
Then:
    uv run python scripts/model_smoke_test.py [--url http://127.0.0.1:8080]

Checks: server healthy; every reply non-empty after cleaning; whether the raw output still
contained reasoning (means thinking was NOT disabled — fix server flags before use);
latency per reply.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from oasis.llm.client import LLMFailure, clean_reply
from oasis.llm.llama_server import LlamaServerClient
from oasis.llm.prompt import build_messages
from oasis.settings import Settings
from oasis.types import Plan

PROMPTS = [
    "I've had a really long week and I feel worn out.",
    "My friend didn't reply to my message and now I feel like nobody cares.",
    "I just want to talk for a bit.",
]


async def main(url: str) -> int:
    s = Settings()
    client = LlamaServerClient(
        base_url=url,
        model=s.llm_model,
        connect_timeout_s=s.llm_connect_timeout_s,
        sampling={
            "temperature": s.llm_temperature,
            "top_p": s.llm_top_p,
            "top_k": s.llm_top_k,
            "min_p": s.llm_min_p,
        },
    )
    if not await client.health():
        print(f"FAIL: llama-server not healthy at {url}")
        await client.aclose()
        return 1

    failures = 0
    plan = Plan(mode="companion", constraints=("one_question", "no_advice"))
    for prompt in PROMPTS:
        messages = build_messages(plan, [], prompt, history_turns=0)
        start = time.perf_counter()
        try:
            raw = await client.generate(
                messages, max_tokens=s.llm_max_tokens, timeout_s=s.llm_generate_timeout_s
            )
            reply = clean_reply(raw)
        except LLMFailure as exc:
            print(f"FAIL ({exc.reason}) for prompt: {prompt!r}")
            failures += 1
            continue
        elapsed = time.perf_counter() - start
        leaked = "<think" in raw.lower() or "</think" in raw.lower()
        if leaked:
            failures += 1
        verdict = "REASONING IN RAW OUTPUT (thinking not disabled)" if leaked else "ok"
        print(f"\n[{elapsed:5.2f}s] {verdict}")
        print(f"  user:  {prompt}")
        print(f"  reply: {reply}")

    await client.aclose()
    print(f"\n{'PASS' if failures == 0 else f'FAIL ({failures})'}")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default=Settings().llm_url)
    sys.exit(asyncio.run(main(parser.parse_args().url)))
