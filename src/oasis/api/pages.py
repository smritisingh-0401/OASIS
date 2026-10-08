"""Server-rendered help card (rules S12, F2).

The crisis resources are rendered into index.html once at startup as plain HTML with
nested <details> elements. Opening the card needs no JavaScript and no network request,
so it keeps working if the backend goes down after the page has loaded. All text is
HTML-escaped; links are user-initiated navigation, not page loads (rules F1).
"""

from __future__ import annotations

from html import escape

from oasis.safety.resources import Country, CrisisLine, Resources, dial_string

MARKER = "<!-- CRISIS_RESOURCES -->"


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


def _country(country: Country) -> str:
    items = [_line(line) for line in country.lines]
    for e in country.emergency:
        numbers = " or ".join(_tel(n) for n in e.numbers)
        items.append(f'<li class="emergency">{escape(e.service)}: {numbers}</li>')
    if country.emergency_note:
        items.append(f'<li class="emergency">{escape(country.emergency_note)}</li>')
    return (
        f'<details class="country" id="crisis-{escape(country.code)}">'
        f"<summary>{escape(country.name)}</summary><ul>{''.join(items)}</ul></details>"
    )


def render_help(resources: Resources) -> str:
    regions = []
    for region in resources.regions:
        countries = [c for c in resources.countries if c.region == region]
        regions.append(
            f'<details class="region"><summary>{escape(region)}</summary>'
            f"{''.join(_country(c) for c in countries)}</details>"
        )
    return (
        '<p class="help-pick">Choose your region and country for crisis lines:</p>'
        + "".join(regions)
        + '<p class="help-fallback">If your country isn\'t listed, call your local emergency '
        "number.</p>"
    )


def render_index(template: str, resources: Resources) -> str:
    if MARKER not in template:
        raise ValueError("index.html is missing the crisis resources marker")
    return template.replace(MARKER, render_help(resources))
