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
