"""Resume section detection (M7).

Offsets are asserted via text.index() of known content lines, so every
expected span is derived from the constructed text itself, not from a
first run's output.
"""

from app.profile.sections import detect_layout

RESUME = """Alex Chen
San Francisco, CA | alex.chen@example.com

Summary
Backend engineer with experience in Python.

Technical Skills:
Python, Go, PostgreSQL

Work Experience
Senior Engineer, Acme
2020 - Present
- Experience with Python in production.

Education
State University
"""


def test_detects_sections_in_order():
    layout = detect_layout(RESUME)
    assert [s.kind for s in layout.sections] == ["summary", "skills", "experience", "education"]


def test_header_block_ends_at_first_section_header():
    layout = detect_layout(RESUME)
    assert layout.header_end == RESUME.index("Summary")
    assert "Alex Chen" in RESUME[: layout.header_end]
    assert "alex.chen@example.com" in RESUME[: layout.header_end]


def test_section_spans_cover_exactly_their_content():
    layout = detect_layout(RESUME)
    skills = layout.section("skills")
    # Content starts on the line after "Technical Skills:" and runs to the
    # start of the "Work Experience" header line.
    assert RESUME[skills.start : skills.end].strip() == "Python, Go, PostgreSQL"
    experience = layout.section("experience")
    assert RESUME[experience.start].isprintable()
    assert RESUME[experience.start : experience.end].startswith("Senior Engineer, Acme")
    assert experience.end == RESUME.index("Education")


def test_content_line_mentioning_experience_is_not_a_header():
    # "- Experience with Python in production." must stay inside the
    # experience section, not open a new one (fullmatch, not prefix).
    layout = detect_layout(RESUME)
    assert len([s for s in layout.sections if s.kind == "experience"]) == 1


def test_header_variants_and_decorations():
    text = "SKILLS\nPython\nEMPLOYMENT HISTORY\nAcme\n• Projects •\nThing built\n"
    layout = detect_layout(text)
    assert [s.kind for s in layout.sections] == ["skills", "experience", "projects"]


def test_no_headers_means_no_sections_and_all_header_block():
    text = "Alex Chen\njust some text\n"
    layout = detect_layout(text)
    assert layout.sections == []
    assert layout.header_end == len(text)
