"""Employment-type classification: the declared-value vocabulary and the
title/description fallback that covers everything sources don't state."""

import pytest

from app.catalog.employment import normalize_declared
from app.extraction.employment import classify_employment_type


class TestNormalizeDeclared:
    @pytest.mark.parametrize(
        ("declared", "expected"),
        [
            ("Full-time", "full_time"),
            ("full time", "full_time"),
            ("FullTime", "full_time"),
            ("Permanent", "full_time"),
            ("Part-time", "part_time"),
            ("Intern", "internship"),
            ("Internship", "internship"),
            ("Co-op", "internship"),
            ("Student", "internship"),
            ("Contract", "contract"),
            ("Contractor", "contract"),
            ("Temporary", "temporary"),
            ("Seasonal", "temporary"),
        ],
    )
    def test_recognized_spellings(self, declared: str, expected: str) -> None:
        assert normalize_declared(declared) == expected

    def test_compound_phrasing_uses_the_meaningful_token(self) -> None:
        assert normalize_declared("Regular Full-Time Employee") == "full_time"
        assert normalize_declared("Intern / Co-op") == "internship"

    @pytest.mark.parametrize("declared", [None, "", "   ", "-", "Tier 2", "Exempt"])
    def test_unrecognized_falls_through_to_none(self, declared: str | None) -> None:
        # None (not a guess) is what lets the caller reach the text
        # classifier instead of inheriting a wrong declared type.
        assert normalize_declared(declared) is None


class TestDeclaredWins:
    def test_declared_outranks_the_title(self) -> None:
        # The source is stating a fact about its own posting; a title
        # heuristic must not overrule it.
        assert (
            classify_employment_type("Backend Software Engineer", declared="Intern")
            == "internship"
        )
        assert (
            classify_employment_type("Software Engineering Intern", declared="Full-time")
            == "full_time"
        )

    def test_unrecognized_declared_falls_back_to_text(self) -> None:
        assert (
            classify_employment_type("Software Engineering Intern", declared="Tier 2")
            == "internship"
        )


class TestInternshipDetection:
    @pytest.mark.parametrize(
        "title",
        [
            "Software Engineering Intern",
            "Intern, Data Science",
            "2027 Summer Intern - Backend",
            "Machine Learning Internship",
            "Engineering Co-op",
            "Co-Op Software Developer",
            "Student Intern, Platform",
            "Summer Student - Research",
            "Graduate Intern, Robotics",
            "Software Engineer Apprentice",
        ],
    )
    def test_internship_titles(self, title: str) -> None:
        assert classify_employment_type(title) == "internship"

    @pytest.mark.parametrize(
        "title",
        [
            "Backend Software Engineer",
            "Internal Tools Engineer",
            "International Payments Engineer",
            "Senior Engineer, Internal Platform",
            "Student Success Manager",
            "Director of Student Programs",
            # New-grad roles are permanent hires, not internships — their
            # entry-level-ness is an experience_level fact, not an
            # employment_type one.
            "New Grad Software Engineer",
            "Software Engineer, New Graduate 2027",
            "University Graduate, Software Engineer",
        ],
    )
    def test_lookalike_titles_are_not_internships(self, title: str) -> None:
        # "internal"/"international" contain "intern"; a student-success
        # role is named after its customers, not its hire.
        assert classify_employment_type(title) != "internship"

    @pytest.mark.parametrize(
        "text",
        [
            "Join our 12-week summer internship program in Pittsburgh.",
            "You must be currently enrolled in an accredited degree program.",
            "This internship runs from May through August.",
            "Open to rising seniors pursuing a Bachelor's in Computer Science.",
            "Our co-op program places students on real product teams.",
        ],
    )
    def test_internship_from_description_when_title_is_silent(self, text: str) -> None:
        assert classify_employment_type("Software Engineer", text) == "internship"

    def test_boilerplate_deep_in_the_body_does_not_flip_the_type(self) -> None:
        # A permanent posting whose footer mentions internships must stay
        # full_time — this is why the body scan is capped.
        body = "We build payments infrastructure. " * 200 + "We also run a summer internship."
        assert classify_employment_type("Staff Backend Engineer", body) == "full_time"


class TestOtherTypes:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Backend Software Engineer", "full_time"),
            ("Senior Platform Engineer", "full_time"),
            ("Part-Time Support Engineer", "part_time"),
            ("Contract Frontend Developer", "contract"),
            ("Freelance Technical Writer", "contract"),
            ("Temporary Data Analyst", "temporary"),
            ("Seasonal Warehouse Associate", "temporary"),
        ],
    )
    def test_titles(self, title: str, expected: str) -> None:
        assert classify_employment_type(title) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("This is a 6-month contract position with possible extension.", "contract"),
            ("We are hiring on a part-time basis, 20 hours per week.", "part_time"),
            ("This is a temporary role covering a parental leave.", "temporary"),
        ],
    )
    def test_descriptions(self, text: str, expected: str) -> None:
        assert classify_employment_type("Software Engineer", text) == expected

    def test_internship_outranks_other_title_markers(self) -> None:
        assert classify_employment_type("Contract Design Intern") == "internship"

    def test_title_outranks_the_description(self) -> None:
        assert (
            classify_employment_type(
                "Software Engineering Intern", "Full-time employees receive equity."
            )
            == "internship"
        )

    def test_nothing_to_classify_is_unknown(self) -> None:
        assert classify_employment_type("", "") == "unknown"
        assert classify_employment_type("   ", "  \n ") == "unknown"
