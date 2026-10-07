"""Crisis resources: shipped file is valid, complete and sourced (design §2.4, rules S14)."""

from __future__ import annotations

import datetime

import pytest

from oasis.safety.resources import dial_string, load_resources
from oasis.safety.rules import SafetyConfigError

RES = load_resources()
BY_CODE = {c.code: c for c in RES.countries}

# Tier 1 countries whose crisis line was confirmed on an official source (memory.md).
TIER_1 = {
    "US", "CA", "MX", "GB", "IE", "FR", "ES", "DE", "IT", "NL", "PL", "SE", "UA", "AU", "NZ",
    "ZA", "NG", "BR", "AR", "PE", "IN", "BD", "LK", "NP", "BT", "MV", "CN", "HK", "TW", "JP",
    "KR", "TH", "MY", "SG", "ID", "BN", "IL", "QA", "SA", "AE",
}  # fmt: skip


def test_every_inhabited_region_is_covered() -> None:
    assert {c.region for c in RES.countries} == set(RES.regions)
    assert len(RES.countries) >= 200


def test_tier_1_countries_have_verified_crisis_lines() -> None:
    with_lines = {c.code for c in RES.countries if c.lines}
    assert with_lines == TIER_1


def test_every_entry_is_sourced_and_dated() -> None:
    for c in RES.countries:
        assert c.emergency_source.startswith("https://")
        assert c.emergency or c.emergency_note
        for line in c.lines:
            assert line.source.startswith("https://")
            assert line.verified_on <= datetime.date.today()


@pytest.mark.parametrize(
    ("code", "number"),
    [("US", "911"), ("GB", "999"), ("AU", "000"), ("NZ", "111"), ("IN", "112")],
)
def test_well_known_emergency_numbers(code: str, number: str) -> None:
    assert any(number in e.numbers for e in BY_CODE[code].emergency)


@pytest.mark.parametrize(
    ("raw", "dial"),
    [("13 11 14", "131114"), ("+603-7627 2929", "+60376272929"), ("16000 (option 4)", "16000"),
     ("119 ext. 8", "119"), ("1800-89-14416", "18008914416"), ("000", "000")],
)  # fmt: skip
def test_dial_string(raw: str, dial: str) -> None:
    assert dial_string(raw) == dial


GOOD = """
version: "t"
regions: [Europe]
countries:
  - code: GB
    name: United Kingdom
    region: Europe
    emergency: [{service: All emergencies, numbers: ["999"]}]
    emergency_source: https://www.gov.uk/x
    emergency_verified_on: 2026-01-01
    lines:
      - {name: Samaritans, phones: ["116 123"], url: "https://s.org", source: "https://s.org",
         verified_on: 2026-01-01}
"""


def test_minimal_file_loads() -> None:
    assert load_resources(GOOD).countries[0].lines[0].phones == ("116 123",)


@pytest.mark.parametrize(
    "bad",
    [
        GOOD.replace("code: GB", "code: gbr"),
        GOOD.replace("region: Europe", "region: Atlantis"),
        GOOD.replace('numbers: ["999"]', 'numbers: ["call the police"]'),
        GOOD.replace("https://www.gov.uk/x", "http://www.gov.uk/x"),
        GOOD.replace('source: "https://s.org"', 'source: "somewhere"'),
        GOOD.replace("emergency_verified_on: 2026-01-01", "emergency_verified_on: 2999-01-01"),
        GOOD.replace('phones: ["116 123"]', "phones: []"),
        GOOD.replace("emergency: [{service: All emergencies, numbers: [\"999\"]}]", "emergency: []"),
        "countries: [",
    ],
)
def test_invalid_resources_refuse_to_load(bad: str) -> None:
    with pytest.raises(SafetyConfigError):
        load_resources(bad)
