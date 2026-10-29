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


def test_the_help_card_fits_a_phone_screen() -> None:
    """At 375 px the card was anchored to the "Need help now?" pill, which sits left of the
    settings button, so it ran 55 px off the left edge: the crisis lines were cut off.
    On narrow screens it spans the header instead, 16 px from each side."""
    narrow = re.search(r"@media \(max-width: 520px\) \{(.*?)\n\}", CSS, re.DOTALL)
    assert narrow is not None
    block = narrow.group(1)
    card = re.search(r"\.help-card \{([^}]*)\}", block)
    assert card is not None
    assert "left: 16px" in card.group(1)
    assert "right: 16px" in card.group(1)
    assert "width: auto" in card.group(1)
    assert re.search(r"\.help \{[^}]*position: static", block)
    assert re.search(r"\.top \{[^}]*position: relative", block)


# --- demo testing, 2026-10-29: fixed chat panel, auto-scroll, typing animation -------------

HTML = (Path(oasis.__file__).parent / "web" / "index.html").read_text(encoding="utf-8")


def test_only_the_conversation_scrolls_so_the_composer_stays_in_view() -> None:
    assert '<body class="chat-page">' in HTML
    page = _rule("body.chat-page")
    assert "height: 100dvh" in page
    assert "overflow: hidden" in page
    conversation = _rule(".chat-page .messages")
    assert "overflow-y: auto" in conversation
    assert "min-height: 0" in conversation


def test_new_messages_follow_a_reader_at_the_bottom_only() -> None:
    """Scrolled up to read, a reader gets a "New message" button instead of being moved."""
    add = re.search(r"function addMessage\(.*?\n\}", JS, re.DOTALL)
    assert add is not None
    assert "atBottom()" in add.group(0)
    assert "follow(stick)" in add.group(0)
    assert 'id="new-message"' in HTML


def test_replies_type_out_but_crisis_replies_never_do() -> None:
    """Typed out word by word, at most TYPE_MAX_MS; crisis replies and reduced motion show
    at once, and a screen reader gets the whole reply once."""
    assert "prefers-reduced-motion: reduce" in JS
    cap = re.search(r"TYPE_MAX_MS = (\d+)", JS)
    assert cap is not None
    assert int(cap.group(1)) <= 2000
    assert 'const animate = body.mode !== "crisis" && body.mode !== "post_crisis"' in JS
    assert 'setAttribute("aria-hidden", "true")' in JS
    assert "msg bot typing" in JS
    assert "prefers-reduced-motion" in CSS
