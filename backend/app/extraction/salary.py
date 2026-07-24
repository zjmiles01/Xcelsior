"""Salary extraction and normalization.

Postings state pay as annual or hourly, single values or ranges, with $ and
k-suffix variations. Both the as-stated form and a normalized annual-USD
form are produced; aggregates only ever use the normalized form, display
shows the raw form. Hourly converts at 2,080 hours/year (documented
assumption). Values outside sanity bounds are rejected rather than stored.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

HOURS_PER_YEAR = 2080

_ANNUAL_MIN, _ANNUAL_MAX = Decimal(20_000), Decimal(1_500_000)
_HOURLY_MIN, _HOURLY_MAX = Decimal(10), Decimal(500)

_AMOUNT = r"\$?\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?\s?[kK]|\d+(?:\.\d+)?)"
_RANGE_RE = re.compile(_AMOUNT + r"\s*(?:-|–|—|\bto\b)\s*" + _AMOUNT)
_UP_TO_RE = re.compile(r"up to\s+" + _AMOUNT, re.IGNORECASE)
_SINGLE_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?\s?[kK])")
_HOURLY_CUE = re.compile(r"per\s+hour|hourly|/\s?hour|/\s?hr\b", re.IGNORECASE)
_ANNUAL_CUE = re.compile(r"per\s+(year|annum)|annual|/\s?year|/\s?yr\b|a year", re.IGNORECASE)
_CUE_WINDOW = 80


@dataclass(frozen=True)
class SalaryExtraction:
    min_amount: Decimal
    max_amount: Decimal
    period: str  # "year" | "hour"
    annual_min: Decimal
    annual_max: Decimal
    currency: str = "USD"


def _parse_amount(raw: str) -> Decimal:
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if cleaned[-1] in "kK":
        return Decimal(cleaned[:-1].strip()) * 1000
    return Decimal(cleaned)


def _classify_period(text: str, pos: int, low: Decimal) -> str | None:
    window = text[max(0, pos - _CUE_WINDOW) : pos + _CUE_WINDOW]
    if _HOURLY_CUE.search(window):
        return "hour"
    if _ANNUAL_CUE.search(window):
        return "year"
    # No explicit cue: infer from magnitude.
    if _HOURLY_MIN <= low <= _HOURLY_MAX:
        return "hour"
    if low >= _ANNUAL_MIN:
        return "year"
    return None


def _validate(low: Decimal, high: Decimal, period: str) -> bool:
    lo_bound, hi_bound = (
        (_HOURLY_MIN, _HOURLY_MAX) if period == "hour" else (_ANNUAL_MIN, _ANNUAL_MAX)
    )
    return lo_bound <= low <= hi_bound and lo_bound <= high <= hi_bound and low <= high


def _build(low: Decimal, high: Decimal, period: str) -> SalaryExtraction:
    factor = HOURS_PER_YEAR if period == "hour" else 1
    return SalaryExtraction(
        min_amount=low,
        max_amount=high,
        period=period,
        annual_min=low * factor,
        annual_max=high * factor,
    )


def extract_salary(text: str) -> SalaryExtraction | None:
    """First plausible range wins; 'up to X' and bare single amounts are
    fallbacks. Returns None rather than guessing when nothing validates."""
    for match in _RANGE_RE.finditer(text):
        low, high = _parse_amount(match.group(1)), _parse_amount(match.group(2))
        # "150-180k" writes the multiplier only once.
        if high >= 1000 > low:
            low *= 1000
        period = _classify_period(text, match.start(), low)
        if period and _validate(low, high, period):
            return _build(low, high, period)

    for match in _UP_TO_RE.finditer(text):
        amount = _parse_amount(match.group(1))
        period = _classify_period(text, match.start(), amount)
        if period and _validate(amount, amount, period):
            return _build(amount, amount, period)

    for match in _SINGLE_RE.finditer(text):
        amount = _parse_amount(match.group(1))
        period = _classify_period(text, match.start(), amount)
        if period and _validate(amount, amount, period):
            return _build(amount, amount, period)

    return None
