"""Server-rendered help card (rules S12, F2) and first-use data notice (FR-PRV-1).

The crisis resources are rendered into index.html once at startup as plain HTML with
nested <details> elements. Opening the card needs no JavaScript and no network request,
so it keeps working if the backend goes down after the page has loaded. The data notice is
rendered the same way. All text is HTML-escaped; links are user-initiated navigation, not
page loads (rules F1).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from typing import Any

from oasis.content import load_yaml, require_review
from oasis.safety.resources import Country, CrisisLine, Resources, dial_string

MARKER = "<!-- CRISIS_RESOURCES -->"
_ZONE = re.compile(r"[A-Za-z0-9_+\-]+(?:/[A-Za-z0-9_+\-]+)+")  # "Asia/Kolkata"
NOTICE_MARKER = "<!-- DATA_NOTICE -->"
COUNTRY_MARKER = "<!-- COUNTRY OPTIONS -->"
DEMO_MARKER = "<!-- DEMO BANNER -->"
DEMO_BANNER = (
    '<p class="demo-banner" role="note"><strong>Test version.</strong> Use made-up messages '
    "only: this is not for real support. If you need help now, call your local emergency "
    "number.</p>"
)


@dataclass(frozen=True)
class Section:
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Disclosure:
    version: str
    title: str
    sections: tuple[Section, ...]
    visible: int  # sections shown before "Read more"
    agreement: str  # always shown, next to the buttons that give consent


def parse_disclosure(raw: Mapping[str, Any]) -> Disclosure:
    require_review(raw, "data notice")
    sections = tuple(
        Section(str(s["heading"]), tuple(str(p) for p in s["paragraphs"]))
        for s in raw.get("sections") or ()
    )
    if not sections or not all(s.heading and s.paragraphs and all(s.paragraphs) for s in sections):
        raise ValueError("data notice needs sections, each with a heading and paragraphs")
    visible, agreement = int(raw["visible_sections"]), str(raw["agreement"])
    if not 1 <= visible <= len(sections) or not agreement:
        raise ValueError("data notice needs 1..len(sections) visible sections and an agreement")
    return Disclosure(str(raw["version"]), str(raw["title"]), sections, visible, agreement)


@functools.cache
def load_disclosure(demo: bool = False) -> Disclosure:
    """The data notice; the online demo has its own, because messages leave the computer."""
    return parse_disclosure(
        load_yaml("privacy", "disclosure_demo.yaml" if demo else "disclosure.yaml")
    )


def _sections(sections: tuple[Section, ...]) -> str:
    return "".join(
        f"<h3>{escape(s.heading)}</h3>" + "".join(f"<p>{escape(p)}</p>" for p in s.paragraphs)
        for s in sections
    )


def render_onboarding(d: Disclosure) -> str:
    more = d.sections[d.visible :]
    folded = (
        f'<details class="notice-more"><summary>Read more</summary>{_sections(more)}</details>'
        if more
        else ""
    )
    return (
        f'<div class="notice" data-version="{escape(d.version)}">'
        f'<h2 id="notice-title">{escape(d.title)}</h2>{_sections(d.sections[: d.visible])}'
        f'{folded}<p class="notice-agreement">{escape(d.agreement)}</p></div>'
    )


def parse_time_zones(raw: Mapping[str, Any]) -> dict[str, str]:
    """Time zone name -> country code (scripts/time_zones.py, decision 2026-10-24)."""
    zones = {str(z): str(c) for z, c in (raw.get("zones") or {}).items()}
    if not raw.get("version") or not zones:
        raise ValueError("time zone map needs a version and zones")
    for zone, code in zones.items():
        if not _ZONE.fullmatch(zone) or not re.fullmatch(r"[A-Z]{2}", code):
            raise ValueError(f"invalid time zone entry: {zone!r}")
    return zones


@functools.cache
def load_time_zones() -> dict[str, str]:
    return parse_time_zones(load_yaml("help", "time_zones.yaml"))


def _tel(number: str) -> str:
    return f'<a href="tel:{escape(dial_string(number))}">{escape(number)}</a>'


def _line(line: CrisisLine) -> str:
    parts = [f"<strong>{escape(line.name)}</strong>", ", ".join(_tel(p) for p in line.phones)]
    if line.text:
        parts.append(f"text {escape(line.text)}")
    if line.hours:
        parts.append(f'<span class="hours">({escape(line.hours)})</span>')
    parts.append(
        f'<a href="{escape(line.url)}" rel="noopener noreferrer" target="_blank">website</a>'
    )
    return '<li class="line">' + " ".join(parts) + "</li>"


def _country(country: Country, zones: str) -> str:
    items = [_line(line) for line in country.lines]
    for e in country.emergency:
        numbers = " or ".join(_tel(n) for n in e.numbers)
        items.append(f'<li class="emergency">{escape(e.service)}: {numbers}</li>')
    if country.emergency_note:
        items.append(f'<li class="emergency">{escape(country.emergency_note)}</li>')
    zone_attr = f' data-zones="{escape(zones)}"' if zones else ""
    return (
        f'<details class="country" id="crisis-{escape(country.code)}"{zone_attr}>'
        f"<summary>{escape(country.name)}</summary><ul>{''.join(items)}</ul></details>"
    )


def render_help(resources: Resources, zones: Mapping[str, str]) -> str:
    """The help card. Each country carries its time zone names, so the page can open the
    computer's own country first without asking anyone (app.js suggestCountry)."""
    by_code: dict[str, list[str]] = {}
    for zone, code in sorted(zones.items()):
        by_code.setdefault(code, []).append(zone)
    regions = []
    for region in resources.regions:
        countries = [c for c in resources.countries if c.region == region]
        regions.append(
            f'<details class="region"><summary>{escape(region)}</summary>'
            f"{''.join(_country(c, ' '.join(by_code.get(c.code, []))) for c in countries)}"
            "</details>"
        )
    # One dropdown, open as rendered so the lines show with no script; app.js folds it under
    # "Not right?" once it has put the time-zone country above. The fallback stays outside.
    return (
        '<details class="all-countries" open><summary>Choose your country</summary>'
        + "".join(regions)
        + "</details>"
        + '<p class="help-fallback">If your country isn\'t listed, call your local emergency '
        "number.</p>"
    )


def render_index(template: str, resources: Resources, disclosure: Disclosure) -> str:
    if MARKER not in template or NOTICE_MARKER not in template:
        raise ValueError("index.html is missing the crisis resources or data notice marker")
    return template.replace(MARKER, render_help(resources, load_time_zones())).replace(
        NOTICE_MARKER, render_onboarding(disclosure)
    )


def render_demo(template: str, demo: bool) -> str:
    """Every page has the banner slot; the online demo fills it."""
    if DEMO_MARKER not in template:
        raise ValueError("page is missing the demo banner marker")
    return template.replace(DEMO_MARKER, DEMO_BANNER if demo else "")


def render_settings(template: str, resources: Resources) -> str:
    """The settings page, with the help card's countries as the choices for its country."""
    if COUNTRY_MARKER not in template:
        raise ValueError("settings.html is missing the country options marker")
    options = ['<option value="">Use this computer\'s time zone</option>'] + [
        f'<option value="{escape(c.code)}">{escape(c.name)}</option>'
        for c in sorted(resources.countries, key=lambda c: c.name)
    ]
    return template.replace(COUNTRY_MARKER, "".join(options))
