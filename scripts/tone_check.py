"""Real-model tone check for companion mode. NOT run in CI (needs model weights).

Start the server first (see scripts/model_smoke_test.py), then:
    uv run python scripts/tone_check.py [--url http://127.0.0.1:8080] [--out FILE]

Each sample message goes through the full engine (safety gate, planner, prompt, reply checks,
one retry, fallback) in its own fresh session. The transcript lists every draft with the
rules it broke, the final reply and whether it fell back, for review against FR-CMP
("validate the feeling, then one gentle question"; no praise, unprompted advice or dependency
language). `--fake` runs the same pipeline against the fake model to check the plumbing.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

from oasis.core.engine import ChatEngine
from oasis.guard.checks import check
from oasis.llm.client import LLMClient
from oasis.llm.fake import FakeLLM
from oasis.llm.llama_server import LlamaServerClient
from oasis.safety.gate import RuleBasedSafetyGate
from oasis.safety.rules import load_ruleset
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.types import GuardVerdict, Plan

SAMPLES = [
    "I've had a really long week and I feel worn out.",
    "My friend cancelled on me again and I'm kind of hurt.",
    "I just want to talk for a bit.",
    "Work has been really stressful lately.",
    "I feel lonely at the weekends.",
    "I got some good news today but I can't really enjoy it.",
    "My exams start next week and I'm nervous.",
    "I had an argument with my mum this morning.",
    "I don't really know how I feel today.",
    "I finally finished a big project.",
    "What should I do about my flatmate never cleaning up?",
    "Any tips for switching off after work?",
]


async def run(url: str, fake: bool) -> list[str] | None:
    """The transcript lines, or None when llama-server is not healthy."""
    s = Settings()
    llm: LLMClient
    if fake:
        llm = FakeLLM()
    else:
        llm = LlamaServerClient(
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
        if not await llm.health():
            print(f"FAIL: llama-server not healthy at {url}")
            await llm.aclose()
            return None

    drafts: list[tuple[str, GuardVerdict]] = []

    def recording_check(draft: str, plan: Plan) -> GuardVerdict:
        verdict = check(draft, plan)
        drafts.append((draft, verdict))
        return verdict

    repo = MemoryRepository()
    engine = ChatEngine(safety=RuleBasedSafetyGate(load_ruleset()), llm=llm, repo=repo,
                        settings=s, guard=recording_check)  # fmt: skip
    lines = ["# Companion tone check", "", f"Model: {'fake' if fake else s.llm_model}", ""]
    first_pass = 0
    for i, message in enumerate(SAMPLES):
        drafts.clear()
        await repo.create_user_session(f"tone-{i}")
        result = await engine.handle_turn(f"tone-{i}", message)
        first_pass += bool(drafts) and drafts[0][1].ok
        lines += [f"## {i + 1}. {message}", "", f"- mode: {result.mode}"]
        for n, (draft, verdict) in enumerate(drafts, 1):
            status = "pass" if verdict.ok else "fail: " + ", ".join(verdict.reasons)
            lines.append(f"- draft {n} ({status}): {draft}")
        lines += [f"- final ({result.fallback_reason or 'generated'}): {result.reply}", ""]
        print(f"{i + 1:2}. {result.fallback_reason or 'ok':15} {result.reply}")
    await llm.aclose()

    lines.insert(4, f"First drafts passing every check: {first_pass}/{len(SAMPLES)}\n")
    print(f"\nFirst drafts passing: {first_pass}/{len(SAMPLES)}")
    return lines


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default=Settings().llm_url)
    parser.add_argument(
        "--out", type=pathlib.Path, default=pathlib.Path("docs/reports/phase-06-tone-check.md")
    )
    parser.add_argument("--fake", action="store_true", help="use the fake model")
    args = parser.parse_args()
    transcript = asyncio.run(run(args.url, args.fake))
    if transcript is None:
        sys.exit(1)
    args.out.write_text("\n".join(transcript), encoding="utf-8")
    print(f"Transcript: {args.out}")
