from decimal import Decimal

from app.extraction.salary import extract_salary


def test_annual_range_with_commas():
    s = extract_salary("Salary range: $170,000 - $210,000 per year.")
    assert s is not None
    assert (s.annual_min, s.annual_max, s.period) == (Decimal(170000), Decimal(210000), "year")


def test_k_suffix_range():
    s = extract_salary("Compensation: $140k–$180k per year DOE.")
    assert s is not None
    assert (s.annual_min, s.annual_max) == (Decimal(140000), Decimal(180000))


def test_single_sided_k_multiplier():
    s = extract_salary("We pay 150-180k annually.")
    assert s is not None
    assert (s.annual_min, s.annual_max) == (Decimal(150000), Decimal(180000))


def test_hourly_range_annualizes():
    s = extract_salary("This contract pays $55 - $70 per hour.")
    assert s is not None
    assert s.period == "hour"
    assert (s.min_amount, s.max_amount) == (Decimal(55), Decimal(70))
    assert (s.annual_min, s.annual_max) == (Decimal(114400), Decimal(145600))


def test_up_to_hourly():
    s = extract_salary("Up to $95/hr for this engagement.")
    assert s is not None
    assert (s.annual_min, s.annual_max) == (Decimal(197600), Decimal(197600))


def test_single_annual_amount():
    s = extract_salary("Base pay of $120K plus equity, paid annually.")
    assert s is not None
    assert (s.annual_min, s.annual_max) == (Decimal(120000), Decimal(120000))


def test_bare_magnitude_inference():
    s = extract_salary("The band is $95,000 to $115,000 for this role.")
    assert s is not None
    assert s.period == "year"


def test_absurd_values_rejected():
    assert extract_salary("Serving 2,000,000 to 3,000,000 requests daily") is None


def test_small_numbers_without_cues_rejected():
    assert extract_salary("Work 3 to 5 days in office") is None


def test_no_salary_returns_none():
    assert extract_salary("Competitive compensation and great benefits.") is None


def test_year_range_not_salary():
    assert extract_salary("From 2019 to 2024 we grew 10x.") is None
