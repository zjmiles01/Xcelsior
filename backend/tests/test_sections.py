from app.extraction.sections import detect_sections, requirement_level_at

DOC = """Our Company
We build things.

What you'll do
• Ship features
• Review code

Requirements
• 5+ years of experience
• Python fluency

Nice to have
• Kubernetes

Benefits
• Health insurance
"""


def test_detects_all_four_sections():
    kinds = [s.kind for s in detect_sections(DOC)]
    assert kinds == ["responsibilities", "required", "preferred", "benefits"]


def test_section_spans_cover_their_content():
    sections = {s.kind: s for s in detect_sections(DOC)}
    required = sections["required"]
    assert "Python fluency" in DOC[required.start : required.end]
    assert "Kubernetes" not in DOC[required.start : required.end]


def test_requirement_level_mapping():
    sections = detect_sections(DOC)
    assert requirement_level_at(sections, DOC.index("Python fluency")) == "required"
    assert requirement_level_at(sections, DOC.index("Kubernetes")) == "preferred"
    assert requirement_level_at(sections, DOC.index("Ship features")) == "mentioned"
    assert requirement_level_at(sections, DOC.index("We build")) == "mentioned"


def test_headers_with_colons_and_case():
    text = "REQUIREMENTS:\nPython experience\n\nBONUS POINTS:\nRedis"
    kinds = [s.kind for s in detect_sections(text)]
    assert kinds == ["required", "preferred"]


def test_no_headers_yields_no_sections():
    assert detect_sections("Just a paragraph about our company culture.") == []
