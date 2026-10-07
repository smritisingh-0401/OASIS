"""The safety layer must not reach the network, the database or the LLM (rules S8).

import-linter covers project and third-party packages; this AST check covers the
standard-library modules that import-linter cannot express reliably.
"""

from __future__ import annotations

import ast
from pathlib import Path

import oasis.safety

FORBIDDEN = {
    "sqlite3",
    "socket",
    "http",
    "urllib",
    "subprocess",
    "asyncio",
    "httpx",
    "fastapi",
    "uvicorn",
    "oasis.llm",
    "oasis.storage",
    "oasis.api",
    "oasis.core",
}


def _imported_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _is_forbidden(name: str) -> bool:
    return any(name == f or name.startswith(f + ".") for f in FORBIDDEN)


def test_safety_package_imports_nothing_forbidden() -> None:
    package_dir = Path(oasis.safety.__file__).parent
    files = list(package_dir.rglob("*.py"))
    assert files
    offenders = {
        f"{path.name}: {name}"
        for path in files
        for name in _imported_names(path)
        if _is_forbidden(name)
    }
    assert offenders == set()
