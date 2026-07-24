"""Contact extraction from the resume header block (M7)."""

from app.profile.contact import extract_email, extract_name, extract_phone

HEADER = "Alex Chen\nSan Francisco, CA | alex.chen@example.com | (415) 555-0100"


def test_extracts_all_three_from_standard_header():
    assert extract_name(HEADER) == "Alex Chen"
    assert extract_email(HEADER) == "alex.chen@example.com"
    assert extract_phone(HEADER) == "(415) 555-0100"


def test_name_with_middle_initial():
    assert extract_name("Mary J. Watson\nmary@example.com") == "Mary J. Watson"


def test_no_name_when_first_line_is_contact_info():
    assert extract_name("alex.chen@example.com | (415) 555-0100\nAlex Chen") is None


def test_lowercase_line_is_not_a_name():
    assert extract_name("alex chen\n") is None


def test_five_tokens_is_not_a_name():
    assert extract_name("Alex Chen Senior Software Engineer\n") is None


def test_phone_formats():
    assert extract_phone("call 415-555-0100 today") == "415-555-0100"
    assert extract_phone("+1 415.555.0100") == "+1 415.555.0100"
    assert extract_phone("no phone here") is None


def test_email_absent():
    assert extract_email("Alex Chen\nSan Francisco") is None
