"""Date-range grammar for resume entries (M7). Every expected date is
written out by hand next to the input that produces it."""

from datetime import date

from app.profile.dates import find_date_range


def test_month_year_to_present():
    r = find_date_range("Mar 2022 - Present")
    assert r.start == date(2022, 3, 1)
    assert r.end is None
    assert r.is_current is True


def test_full_month_names_with_to_separator():
    r = find_date_range("July 2019 to Feb 2022")
    assert r.start == date(2019, 7, 1)
    assert r.end == date(2022, 2, 1)
    assert r.is_current is False


def test_numeric_month_slash_year():
    r = find_date_range("03/2020 - 06/2023")
    assert r.start == date(2020, 3, 1)
    assert r.end == date(2023, 6, 1)


def test_bare_year_range():
    r = find_date_range("2015 - 2019")
    assert r.start == date(2015, 1, 1)
    assert r.end == date(2019, 1, 1)


def test_dotted_sept_and_en_dash():
    r = find_date_range("Sept. 2018 – Dec 2018")
    assert r.start == date(2018, 9, 1)
    assert r.end == date(2018, 12, 1)


def test_match_span_covers_exactly_the_range():
    line = "Acme Corp | Senior Engineer | Jan 2020 - Dec 2021"
    r = find_date_range(line)
    assert line[r.match_start : r.match_end] == "Jan 2020 - Dec 2021"


def test_reversed_range_is_not_trusted():
    assert find_date_range("2020 - 2018") is None


def test_no_date_returns_none():
    assert find_date_range("Senior Software Engineer") is None


def test_range_found_inside_prose():
    # The grammar finds ranges anywhere; deciding whether a line is an
    # entry anchor is the experience parser's job, not the grammar's.
    r = find_date_range("I worked there from May 2020 until present, remotely.")
    assert r.start == date(2020, 5, 1)
    assert r.is_current is True
