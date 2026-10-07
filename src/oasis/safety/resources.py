"""Crisis and emergency contacts (design §2.4, CR-04).

Loaded and validated once at startup; any problem raises SafetyConfigError so the app
refuses to start rather than show a broken help card. Every entry must carry the official
source it was verified against and the verification date.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml

from oasis.safety.rules import SafetyConfigError

_CODE = re.compile(r"^[A-Z]{2}$")
_EMERGENCY_NUMBER = re.compile(r"^\+?[\d ()-]+$")
# Crisis lines may add a menu option or extension: "16000 (option 4)", "119 ext. 8".
_LINE_NUMBER = re.compile(r"^\+?[\d ()*.-]+(?: ?\((?:option|ext\.?) ?\d+\))?$|^\d+ ext\. \d+$")
_DIAL_PREFIX = re.compile(r"^\+?[\d ()*.-]+?(?=\s*(?:\(|ext\.|$))")


@dataclass(frozen=True)
class Emergency:
    service: str
    numbers: tuple[str, ...]


@dataclass(frozen=True)
class CrisisLine:
    name: str
    phones: tuple[str, ...]
    text: str | None
    hours: str | None
    url: str
    source: str
    verified_on: datetime.date


@dataclass(frozen=True)
class Country:
    code: str
    name: str
    region: str
    emergency: tuple[Emergency, ...]
    emergency_note: str | None
    emergency_source: str
    emergency_verified_on: datetime.date
    lines: tuple[CrisisLine, ...]


@dataclass(frozen=True)
class Resources:
    version: str
    regions: tuple[str, ...]
    countries: tuple[Country, ...]


def dial_string(number: str) -> str:
    """Digits (and a leading +) for a tel: link; menu options and extensions are dropped."""
    match = _DIAL_PREFIX.match(number)
    head = match.group(0) if match else number
    return ("+" if head.startswith("+") else "") + re.sub(r"\D", "", head)


def _https(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.startswith("https://"):
        raise SafetyConfigError(f"{where}: source/url must be an https URL")
    return value


def _date(value: Any, where: str, today: datetime.date) -> datetime.date:
    if not isinstance(value, datetime.date) or value > today:
        raise SafetyConfigError(f"{where}: verified_on must be a date not in the future")
    return value


def _line(raw: dict[str, Any], where: str, today: datetime.date) -> CrisisLine:
    phones = tuple(str(p) for p in raw.get("phones") or ())
    if not raw.get("name") or not phones or not all(_LINE_NUMBER.match(p) for p in phones):
        raise SafetyConfigError(f"{where}: crisis line needs a name and valid phone numbers")
    return CrisisLine(
        name=str(raw["name"]),
        phones=phones,
        text=raw.get("text"),
        hours=raw.get("hours") or None,
        url=_https(raw.get("url"), where),
        source=_https(raw.get("source"), where),
        verified_on=_date(raw.get("verified_on"), where, today),
    )


def _country(raw: dict[str, Any], regions: tuple[str, ...], today: datetime.date) -> Country:
    code = str(raw.get("code", ""))
    where = f"resources.yaml {code or '?'}"
    if not _CODE.match(code) or not raw.get("name") or raw.get("region") not in regions:
        raise SafetyConfigError(f"{where}: needs an ISO code, a name and a known region")
    emergency = tuple(
        Emergency(str(e["service"]), tuple(str(n) for n in e["numbers"]))
        for e in raw.get("emergency") or ()
    )
    if any(not e.numbers or not all(_EMERGENCY_NUMBER.match(n) for n in e.numbers)
           for e in emergency):  # fmt: skip
        raise SafetyConfigError(f"{where}: invalid emergency number")
    note = raw.get("emergency_note")
    if not emergency and not note:
        raise SafetyConfigError(f"{where}: needs emergency numbers or an emergency_note")
    return Country(
        code=code,
        name=str(raw["name"]),
        region=str(raw["region"]),
        emergency=emergency,
        emergency_note=note,
        emergency_source=_https(raw.get("emergency_source"), where),
        emergency_verified_on=_date(raw.get("emergency_verified_on"), where, today),
        lines=tuple(_line(line, where, today) for line in raw.get("lines") or ()),
    )


def load_resources(text: str | None = None, *, today: datetime.date | None = None) -> Resources:
    if text is None:
        text = (resources.files("oasis.content") / "safety" / "resources.yaml").read_text(
            encoding="utf-8"
        )
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SafetyConfigError(f"resources.yaml: invalid YAML: {exc}") from None
    if not isinstance(doc, dict) or not doc.get("countries") or not doc.get("regions"):
        raise SafetyConfigError("resources.yaml: needs regions and countries")
    regions = tuple(doc["regions"])
    today = today or datetime.date.today()
    countries = tuple(_country(c, regions, today) for c in doc["countries"])
    codes = [c.code for c in countries]
    if len(codes) != len(set(codes)):
        raise SafetyConfigError("resources.yaml: duplicate country code")
    return Resources(str(doc.get("version", "")), regions, countries)
