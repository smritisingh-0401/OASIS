"""Server-rendered help card (rules S12, F1): escaped text, tel: links, required marker."""

from __future__ import annotations

import re
import runpy
from pathlib import Path

import pytest
import yaml

from oasis.api.pages import (
    MARKER,
    NOTICE_MARKER,
    load_disclosure,
    load_time_zones,
    parse_time_zones,
    render_help,
    render_index,
)
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


# --- country suggested from the computer's time zone (2026-10-24) -----------------------------

ROOT = Path(__file__).resolve().parents[2]


def test_time_zones_map_to_their_country() -> None:
    zones = load_time_zones()
    for zone, code in [("Asia/Kolkata", "IN"), ("America/New_York", "US"),
                       ("Europe/London", "GB"), ("Australia/Sydney", "AU")]:  # fmt: skip
        assert zones[zone] == code, zone
    # Browsers may report an older name (Chrome: "Asia/Calcutta"); it maps the same way.
    assert zones["Asia/Calcutta"] == "IN"
    assert zones["Europe/Kiev"] == "UA"
    assert all(len(c) == 2 and c.isupper() for c in zones.values())


def test_names_shared_by_several_countries_are_left_out() -> None:
    zones = load_time_zones()
    for name in ("CET", "UTC", "Etc/UTC", "GMT", "Etc/GMT+5"):
        assert name not in zones, name


def test_the_map_is_exactly_what_the_script_builds() -> None:
    """No hand edits: the committed file is the script's output for the pinned tzdata."""
    build = runpy.run_path(str(ROOT / "scripts" / "time_zones.py"))["build"]
    raw = yaml.safe_load((ROOT / "src/oasis/content/help/time_zones.yaml").read_text("utf-8"))
    assert build() == raw["zones"]


def test_each_country_carries_its_zones_on_the_card() -> None:
    zones = {"Asia/Kolkata": "IN", "Asia/Calcutta": "IN", "Europe/London": "GB"}
    html = render_help(load_resources(), zones)
    india = re.search(r'<details class="country" id="crisis-IN"([^>]*)>', html)
    assert india is not None
    assert india.group(1) == ' data-zones="Asia/Calcutta Asia/Kolkata"'
    assert 'id="crisis-GB" data-zones="Europe/London"' in html
    assert re.search(r'id="crisis-AF">', html)  # no zone given: no attribute


def test_every_zone_points_to_at_most_one_country_on_the_page() -> None:
    html = render_help(load_resources(), load_time_zones())
    seen = [z for attr in re.findall(r'data-zones="([^"]*)"', html) for z in attr.split()]
    assert len(seen) == len(set(seen))
    assert "Asia/Calcutta" in seen


def test_an_invalid_time_zone_file_is_rejected() -> None:
    with pytest.raises(ValueError, match="time zone"):
        parse_time_zones({"version": "x", "source": "s", "zones": {"Asia/Kolkata": "india"}})
    with pytest.raises(ValueError, match="time zone"):
        parse_time_zones({"version": "x", "source": "s", "zones": {'Bad"Zone': "IN"}})


def test_the_suggestion_is_worked_out_in_the_page() -> None:
    """Read from the browser's clock settings; never sent anywhere, so it works offline."""
    import oasis

    js = (Path(oasis.__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
    body = js[js.index("function suggestCountry") :]
    body = body[: body.index("\n}\n")]
    assert "resolvedOptions().timeZone" in body
    assert "data-zones" in body
    assert "fetch" not in body
    assert "Not right?" in body
