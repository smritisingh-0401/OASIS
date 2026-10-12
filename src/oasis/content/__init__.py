"""Read-only content library: versioned YAML data files, never user data."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import resources
from typing import Any

import yaml

REVIEW = "needs_clinician_review"


def load_yaml(*parts: str) -> Any:
    """Parse one packaged content file, e.g. load_yaml("router", "weights.yaml")."""
    return yaml.safe_load(resources.files(__name__).joinpath(*parts).read_text(encoding="utf-8"))


def require_review(raw: Mapping[str, Any], what: str) -> None:
    """Every content file or item has a version and is flagged for clinician review (CL6)."""
    if not raw.get("version") or raw.get("review_status") != REVIEW:
        raise ValueError(f"{what} needs a version and review_status: {REVIEW} (rules CL6)")
