"""Export the Mermaid diagrams in the docs to SVG and PNG for reports (PRD O6). NOT run in CI.

    uv run python scripts/export_diagrams.py [--browser PATH]

Needs Node.js. Runs a pinned mermaid-cli through npx, rendering with a Chrome or Edge already
on the computer (puppeteer's own browser download is skipped). Each diagram is named after
the section it sits in: docs/images/<doc>-<section>.svg and .png.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ["architecture.md", "design.md"]
OUT = ROOT / "docs" / "images"
MERMAID_CLI = "@mermaid-js/mermaid-cli@11.17.0"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
]
_BLOCK = re.compile(r"^## (.+?)$|^```mermaid\n(.*?)^```", re.M | re.S)


def diagrams(doc: pathlib.Path) -> list[tuple[str, str]]:
    """(name, source) for each Mermaid block, named after the nearest `##` heading."""
    found: list[tuple[str, str]] = []
    section = ""
    for m in _BLOCK.finditer(doc.read_text(encoding="utf-8")):
        if m.group(1):
            # "3. Request flow for one message (8 stages)" -> "request-flow-for-one-message"
            title = re.sub(r"^[\d.]+\s*|\s*\(.*", "", m.group(1)).lower()
            section = re.sub(r"[^a-z0-9]+", "-", title).strip("-")
        else:
            found.append((f"{doc.stem}-{section}", m.group(2)))
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", help="Chrome or Edge executable (default: first found)")
    args = parser.parse_args()
    browser = args.browser or next(b for b in BROWSERS if pathlib.Path(b).exists())
    npx = shutil.which("npx")
    if npx is None:
        raise SystemExit("npx not found: install Node.js")
    env = {**os.environ, "PUPPETEER_SKIP_DOWNLOAD": "1"}
    with tempfile.TemporaryDirectory() as tmp:
        config = pathlib.Path(tmp, "puppeteer.json")
        config.write_text(json.dumps({"executablePath": browser}), encoding="utf-8")
        for doc in DOCS:
            for name, source in diagrams(ROOT / "docs" / doc):
                src = pathlib.Path(tmp, f"{name}.mmd")
                src.write_text(source, encoding="utf-8")
                for ext, extra in (("svg", []), ("png", ["--scale", "2"])):
                    out = OUT / f"{name}.{ext}"
                    cmd = [
                        npx,
                        "-y",
                        MERMAID_CLI,
                        "-q",
                        "-p",
                        str(config),
                        "-b",
                        "white",
                        "-i",
                        str(src),
                        "-o",
                        str(out),
                        *extra,
                    ]
                    subprocess.run(cmd, check=True, env=env)
                    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
