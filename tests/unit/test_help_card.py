"""Server-rendered help card (rules S12, F1): escaped text, tel: links, required marker."""

from __future__ import annotations

import pytest

from oasis.api.pages import MARKER, NOTICE_MARKER, load_disclosure, render_index
from oasis.safety.resources import load_resources

HOSTILE = """
version: "t"
regions: ["Europe <r>"]
countries:
  - code: GB
    name: "Kingdom <script>"
    region: "Europe <r>"
    emergency: [{service: "Police & <b>", numbers: ["999"]}]
    emergency_source: https://www.gov.uk/x
    emergency_verified_on: 2026-01-01
    lines:
      - {name: "Line <img>", phones: ["116 123 (option 4)"], text: "<t>", hours: "<h>",
         url: "https://s.org/?a=1&b=2", source: "https://s.org", verified_on: 2026-01-01}
"""


def test_every_text_field_is_escaped_and_numbers_are_dialable() -> None:
    template = f"<body>{MARKER}{NOTICE_MARKER}</body>"
    html = render_index(template, load_resources(HOSTILE), load_disclosure())
    for raw in ("<script>", "<img>", "<b>", "<t>", "<h>", "<r>"):
        assert raw not in html
        assert raw.replace("<", "&lt;").replace(">", "&gt;") in html
    assert 'href="https://s.org/?a=1&amp;b=2"' in html
    assert 'href="tel:116123">116 123 (option 4)</a>' in html
    assert 'href="tel:999"' in html


@pytest.mark.parametrize("body", ["", MARKER, NOTICE_MARKER])
def test_template_without_both_markers_is_rejected(body: str) -> None:
    with pytest.raises(ValueError, match="marker"):
        render_index(f"<body>{body}</body>", load_resources(HOSTILE), load_disclosure())
