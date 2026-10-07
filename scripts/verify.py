"""The one verify command: lint, format, types, import rules, security, audit, tests + coverage.

Usage:  uv run python scripts/verify.py
Exit code is non-zero if any step fails. Every step runs, so one report shows everything.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Safety-critical packages held to a higher bar (rules T5); checked once they exist.
CRITICAL_PACKAGES = {"safety": 95.0, "assessment": 95.0, "router": 95.0}


def run(name: str, cmd: list[str]) -> bool:
    print(f"\n=== {name}: {' '.join(cmd)}", flush=True)
    start = time.perf_counter()
    ok = subprocess.run(cmd, cwd=ROOT, check=False).returncode == 0
    print(
        f"=== {name}: {'PASS' if ok else 'FAIL'} ({time.perf_counter() - start:.1f}s)", flush=True
    )
    return ok


def package_coverage(coverage_json: Path) -> bool:
    print("\n=== per-package coverage (critical packages)", flush=True)
    files = json.loads(coverage_json.read_text(encoding="utf-8"))["files"]
    ok = True
    for package, threshold in CRITICAL_PACKAGES.items():
        marker = f"oasis/{package}/"
        summaries = [f["summary"] for path, f in files.items() if marker in path.replace("\\", "/")]
        if not summaries:
            print(f"  {package:<11} not built yet")
            continue
        covered = sum(s["covered_lines"] + s.get("covered_branches", 0) for s in summaries)
        total = sum(s["num_statements"] + s.get("num_branches", 0) for s in summaries)
        pct = 100.0 * covered / total if total else 100.0
        passed = pct >= threshold
        ok &= passed
        print(
            f"  {package:<11} {pct:6.2f}%  (need {threshold:.0f}%)  {'PASS' if passed else 'FAIL'}"
        )
    print(f"=== per-package coverage: {'PASS' if ok else 'FAIL'}", flush=True)
    return ok


def main() -> int:
    py = sys.executable
    with tempfile.TemporaryDirectory() as tmp:
        reqs = Path(tmp) / "requirements.txt"
        cov = Path(tmp) / "coverage.json"
        results = {
            "ruff lint": run("ruff lint", [py, "-m", "ruff", "check", "."]),
            "ruff format": run("ruff format", [py, "-m", "ruff", "format", "--check", "."]),
            "mypy (strict)": run("mypy (strict)", [py, "-m", "mypy", "src/oasis", "scripts"]),
            "import-linter": run("import-linter", ["lint-imports"]),
            "bandit": run(
                "bandit", [py, "-m", "bandit", "-q", "-c", "pyproject.toml", "-r", "src"]
            ),
            # Audit exactly what the lockfile pins, with hashes, without touching pip.
            "pip-audit": run(
                "uv export",
                [
                    os.environ.get("UV", "uv"),
                    "export",
                    "--quiet",
                    "--no-emit-project",
                    "--format",
                    "requirements-txt",
                    "-o",
                    str(reqs),
                ],
            )
            and run(
                "pip-audit",
                [
                    py,
                    "-m",
                    "pip_audit",
                    "-r",
                    str(reqs),
                    "--require-hashes",
                    "--disable-pip",
                    "--progress-spinner",
                    "off",
                ],
            ),
            "pytest + coverage": run(
                "pytest + coverage",
                [
                    py,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "--cov",
                    "--cov-report=term",
                    f"--cov-report=json:{cov}",
                ],
            ),
        }
        results["critical coverage"] = cov.exists() and package_coverage(cov)

    print("\n=== SUMMARY")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
