import pytest

from app.extraction.taxonomy import load_index
from app.extraction.title import canonicalize_title


@pytest.fixture(scope="module")
def index():
    return load_index()


@pytest.mark.parametrize(
    ("raw", "expected_slug", "expected_level"),
    [
        ("Senior Backend Engineer", "backend-engineer", "senior"),
        ("Backend Engineer II", "backend-engineer", "mid"),
        ("Sr. Software Engineer", "software-engineer", "senior"),
        ("Staff Machine Learning Engineer", "machine-learning-engineer", "staff_plus"),
        ("Principal Engineer, Storage", None, "staff_plus"),
        ("Software Engineer, Infrastructure", "infrastructure-engineer", None),
        ("Software Engineer, Backend", "backend-engineer", None),
        ("Java Developer - Payments", "software-engineer", None),
        ("Streaming Platform Engineer", "platform-engineer", None),
        ("QA Automation Engineer", "qa-engineer", None),
        ("Software Engineer in Test", "qa-engineer", None),
        ("Junior Web Developer", "frontend-engineer", "entry"),
        ("Platform Engineer II - Developer Experience", "platform-engineer", "mid"),
        ("Software Engineer L5", "software-engineer", "senior"),
        ("SRE", "site-reliability-engineer", None),
        ("Full Stack Developer (Remote)", "full-stack-engineer", None),
        ("Engineering Manager, Payments", "engineering-manager", None),
        ("Marketing Operations Manager", None, None),
        ("Account Executive", None, None),
    ],
)
def test_canonicalization(index, raw, expected_slug, expected_level):
    result = canonicalize_title(raw, index)
    assert result.canonical_slug == expected_slug
    assert result.level == expected_level


def test_specific_family_beats_generic(index):
    # Both "software engineer" and a specific family match; specific wins.
    result = canonicalize_title("Software Engineer, Data Platform", index)
    assert result.canonical_slug == "data-engineer"


def test_normalized_form_is_reported_for_review(index):
    result = canonicalize_title("Senior Widget Wrangler III", index)
    assert result.canonical_slug is None
    assert result.normalized == "widget wrangler"
    assert result.level == "senior"
