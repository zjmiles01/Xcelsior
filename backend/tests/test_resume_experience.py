"""Experience-entry parsing (M7).

Expected values are hand-derived from the constructed section text in
each test; spans are asserted through text.index() so the truth comes
from the input, never from a first run's output.
"""

from datetime import date

from app.profile.experience import parse_experience

HEADER = "Experience\n"

TWO_ENTRIES = (
    HEADER
    + """Senior Software Engineer, Wavelength Analytics
Mar 2022 - Present
- Designed a Kafka pipeline.
- Led migration to FastAPI.
Software Engineer, Harborview Systems
Jul 2019 - Feb 2022
- Built billing services.
"""
)


def _parse(text: str):
    return parse_experience(text, len(HEADER), len(text))


def test_splits_title_comma_company_entries():
    first, second = _parse(TWO_ENTRIES)

    assert first.title_raw == "Senior Software Engineer"
    assert first.company == "Wavelength Analytics"
    assert first.dates.start == date(2022, 3, 1)
    assert first.dates.is_current is True
    assert first.summary == "- Designed a Kafka pipeline.\n- Led migration to FastAPI."

    assert second.title_raw == "Software Engineer"
    assert second.company == "Harborview Systems"
    assert second.dates.start == date(2019, 7, 1)
    assert second.dates.end == date(2022, 2, 1)
    assert second.summary == "- Built billing services."


def test_entry_spans_partition_at_the_next_heading():
    first, second = _parse(TWO_ENTRIES)
    assert first.start == TWO_ENTRIES.index("Senior Software Engineer")
    assert first.end == TWO_ENTRIES.index("- Led migration to FastAPI.") + len(
        "- Led migration to FastAPI."
    )
    assert second.start == TWO_ENTRIES.index("Software Engineer, Harborview")
    # Evidence round-trip: the span reproduces the entry's own text.
    assert TWO_ENTRIES[first.start : first.end].startswith("Senior Software Engineer")
    assert "Harborview" not in TWO_ENTRIES[first.start : first.end]


def test_single_line_pipe_format():
    text = HEADER + "Acme Corp | Senior Engineer | Jan 2020 - Dec 2021\n- Did things.\n"
    (entry,) = _parse(text)
    assert entry.title_raw == "Senior Engineer"
    assert entry.company == "Acme Corp"
    assert entry.dates.start == date(2020, 1, 1)
    assert entry.dates.end == date(2021, 12, 1)


def test_company_first_comma_order_is_resolved_by_role_words():
    text = HEADER + "Harborview Systems, Software Engineer\n2019 - 2022\n"
    (entry,) = _parse(text)
    assert entry.title_raw == "Software Engineer"
    assert entry.company == "Harborview Systems"


def test_two_line_heading():
    text = HEADER + "Senior Software Engineer\nWavelength Analytics\nMar 2022 - Present\n"
    (entry,) = _parse(text)
    assert entry.title_raw == "Senior Software Engineer"
    assert entry.company == "Wavelength Analytics"


def test_title_only_heading_keeps_company_none():
    text = HEADER + "Freelance Developer\n2018 - 2020\n"
    (entry,) = _parse(text)
    assert entry.title_raw == "Freelance Developer"
    assert entry.company is None


def test_ambiguous_heading_is_kept_whole_not_guessed():
    # Both comma parts contain role words; splitting would be a guess, so
    # the whole heading becomes title_raw and company stays None.
    text = HEADER + "Engineering Manager, Developer Tools\n2020 - 2023\n"
    (entry,) = _parse(text)
    assert entry.title_raw == "Engineering Manager, Developer Tools"
    assert entry.company is None


def test_date_inside_bullet_does_not_split_entry():
    text = (
        HEADER
        + """Software Engineer, Acme
2019 - Present
- Shipped the migration (Jan 2021 - Mar 2021) on time.
"""
    )
    entries = _parse(text)
    assert len(entries) == 1
    assert "Shipped the migration" in entries[0].summary


def test_prose_line_with_dates_is_not_an_anchor():
    text = HEADER + (
        "The team grew significantly and I mentored several new engineers "
        "hired between January 2020 and December 2021 across two offices.\n"
    )
    assert _parse(text) == []
