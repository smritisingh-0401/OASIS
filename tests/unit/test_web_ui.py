"""Front-end behaviour found in the Phase 13 usability review, checked in the script source
(the project has no browser test runner; each was also checked in the browser)."""

from __future__ import annotations

import re
from pathlib import Path

import oasis

JS = (Path(oasis.__file__).parent / "web" / "app.js").read_text(encoding="utf-8")


def test_enter_does_not_send_while_a_reply_is_pending() -> None:
    """Enter calls requestSubmit(), which submits even with Send disabled: the handler must
    refuse, so a second message never goes out without the first in its history."""
    handler = re.search(r'form\.addEventListener\("submit".*?\n\}\);', JS, re.DOTALL)
    assert handler is not None
    assert "sendButton.disabled" in handler.group(0)


def test_escape_closes_the_help_card_and_returns_focus() -> None:
    """The help card opens over the chat; Escape closes it and puts focus back on
    "Need help now?" (WAI-ARIA disclosure used as a pop-up)."""
    handler = re.search(r'"Escape".*?\n\}\);', JS, re.DOTALL)
    assert handler is not None
    assert "help.open = false" in handler.group(0)
    assert 'help.querySelector("summary").focus()' in handler.group(0)


CSS = (Path(oasis.__file__).parent / "web" / "styles.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    found = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", CSS)
    assert found is not None, selector
    return found.group(1)


def test_small_controls_meet_the_24px_target_size() -> None:
    """WCAG 2.2 2.5.8: "Why this reply?" measured 114x22 at 375 px; the help card's phone
    numbers ("15", "112") 20-31 px wide. Both get a 24 px minimum."""
    assert "min-height: 24px" in _rule(".why summary")
    phone = _rule(".help-card a")
    assert "min-height: 24px" in phone
    assert "min-width: 24px" in phone
