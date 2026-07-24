"""Education-entry parsing (M7). Expected values hand-derived per test."""

from app.profile.education import parse_education

HEADER = "Education\n"


def _parse(text: str):
    return parse_education(text, len(HEADER), len(text))


def test_institution_then_degree_line():
    text = HEADER + "University of California, Berkeley\nB.S. in Computer Science, 2015 - 2019\n"
    (entry,) = _parse(text)
    assert entry.institution == "University of California, Berkeley"
    assert entry.degree_raw == "B.S. in Computer Science"
    assert entry.degree_level == "bachelor"
    assert entry.field_of_study == "Computer Science"
    assert entry.start_year == 2015
    assert entry.end_year == 2019


def test_worded_master_degree_and_single_year():
    text = HEADER + "Stanford University\nMaster of Science in Machine Learning, 2021\n"
    (entry,) = _parse(text)
    assert entry.degree_level == "master"
    assert entry.field_of_study == "Machine Learning"
    assert entry.start_year is None
    assert entry.end_year == 2021


def test_two_degrees_same_institution_become_two_entries():
    text = HEADER + (
        "Stanford University\n"
        "M.S. in Computer Science, 2021\n"
        "B.S. in Mathematics, 2019\n"
    )
    ms, bs = _parse(text)
    assert ms.institution == "Stanford University"
    assert ms.degree_level == "master"
    assert ms.end_year == 2021
    assert bs.institution == "Stanford University"
    assert bs.degree_level == "bachelor"
    assert bs.field_of_study == "Mathematics"
    assert bs.end_year == 2019


def test_degree_without_institution():
    text = HEADER + "B.S. in Computer Science, 2015 - 2019\n"
    (entry,) = _parse(text)
    assert entry.institution is None
    assert entry.degree_level == "bachelor"


def test_state_abbreviation_is_not_a_masters_degree():
    # "MA" the state must not read as a Master of Arts (abbreviations are
    # matched case-sensitively and bare MA is excluded outright).
    text = HEADER + "Northeastern University, Boston, MA\nB.S. in Biology, 2018\n"
    (entry,) = _parse(text)
    assert entry.degree_level == "bachelor"
    assert entry.institution == "Northeastern University, Boston, MA"


def test_entry_spans_index_into_the_full_text():
    text = HEADER + "State University\nB.A. in History, 2010 - 2014\n"
    (entry,) = _parse(text)
    assert text[entry.start : entry.end] == "State University\nB.A. in History, 2010 - 2014"


def test_phd():
    text = HEADER + "MIT\nPh.D. in Physics, 2016 - 2022\n"
    entries = _parse(text)
    # "MIT" carries no institution keyword; conservative parsing keeps it
    # out rather than guessing, and the degree line anchors the entry.
    (entry,) = entries
    assert entry.degree_level == "doctorate"
    assert entry.field_of_study == "Physics"
