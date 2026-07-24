import pytest

from app.extraction.matcher import TechnologyMatcher
from app.extraction.taxonomy import load_index


@pytest.fixture(scope="module")
def matcher() -> TechnologyMatcher:
    return TechnologyMatcher(load_index())


def accepted_slugs(matcher: TechnologyMatcher, text: str) -> set[str]:
    accepted, _ = matcher.score(text, matcher.find(text))
    return {t.tech_slug for t in accepted}


class TestDangerousTokens:
    def test_go_in_tech_list_matches(self, matcher):
        slugs = accepted_slugs(matcher, "Experience with Go, Python, and Kubernetes")
        assert "go" in slugs

    def test_go_to_market_does_not_match(self, matcher):
        slugs = accepted_slugs(matcher, "Drive our go-to-market strategy and go further.")
        assert "go" not in slugs

    def test_lowercase_go_never_matches(self, matcher):
        slugs = accepted_slugs(matcher, "We go deep on engineering experience and coding.")
        assert "go" not in slugs

    def test_r_with_context_matches(self, matcher):
        slugs = accepted_slugs(matcher, "Proficiency in R for statistical programming")
        assert "r" in slugs

    def test_r_and_d_does_not_match(self, matcher):
        slugs = accepted_slugs(matcher, "Join our R&D organization with deep experience.")
        assert "r" not in slugs

    def test_c_in_objective_c_does_not_match_c(self, matcher):
        slugs = accepted_slugs(matcher, "Experience with Objective-C codebases required")
        assert "objective-c" in slugs
        assert "c" not in slugs

    def test_c_slash_cpp_matches_both(self, matcher):
        slugs = accepted_slugs(matcher, "Expert-level C/C++ for embedded programming")
        assert {"c", "cpp"} <= slugs

    def test_c_not_matched_inside_csharp(self, matcher):
        slugs = accepted_slugs(matcher, "Strong C# programming experience")
        assert "csharp" in slugs
        assert "c" not in slugs

    def test_swift_language_vs_adverb(self, matcher):
        assert "swift" in accepted_slugs(matcher, "iOS development with Swift and SwiftUI")
        assert "swift" not in accepted_slugs(
            matcher, "We take swift action for customers with experience."
        )

    def test_spring_framework_vs_season(self, matcher):
        assert "spring" in accepted_slugs(matcher, "Java services built on Spring Boot")
        assert "spring" not in accepted_slugs(
            matcher, "Our internship program starts in spring 2027 with experience."
        )

    def test_payment_rails_does_not_match_rails(self, matcher):
        slugs = accepted_slugs(matcher, "Build payment rails with engineering experience")
        assert "rails" not in slugs

    def test_ruby_on_rails_matches_rails_not_ruby_alone(self, matcher):
        slugs = accepted_slugs(matcher, "Production experience with Ruby on Rails")
        assert "rails" in slugs
        assert "ruby" not in slugs  # contained span suppressed

    def test_ray_capitalized_in_ml_context(self, matcher):
        assert "ray" in accepted_slugs(matcher, "Distributed training with Ray and PyTorch")
        assert "ray" not in accepted_slugs(
            matcher, "A ray of sunshine hit the office; great experience."
        )


class TestBoundaries:
    def test_java_not_matched_inside_javascript(self, matcher):
        slugs = accepted_slugs(matcher, "Frontend experience with JavaScript frameworks")
        assert "javascript" in slugs
        assert "java" not in slugs

    def test_sql_not_matched_inside_postgresql(self, matcher):
        slugs = accepted_slugs(matcher, "Deep PostgreSQL experience")
        assert "postgresql" in slugs
        assert "sql" not in slugs

    def test_hyphenated_compound_keeps_long_alias(self, matcher):
        slugs = accepted_slugs(matcher, "PostgreSQL-backed services experience")
        assert "postgresql" in slugs

    def test_punctuation_boundaries_accept(self, matcher):
        slugs = accepted_slugs(matcher, "Our stack: Python, Django, PostgreSQL.")
        assert {"python", "django", "postgresql"} <= slugs


class TestEvidence:
    def test_evidence_contains_the_match_line(self, matcher):
        text = "Requirements\n• Deep experience with Kafka at scale\n• SQL fluency"
        accepted, _ = matcher.score(text, matcher.find(text))
        kafka = next(t for t in accepted if t.tech_slug == "kafka")
        assert "Kafka at scale" in kafka.evidence


class TestDottedAcronyms:
    def test_usc_legal_citation_does_not_match_c(self, matcher):
        text = (
            "To conform to U.S. Government export regulations, applicant must "
            "be a U.S. citizen as defined by 8 U.S.C. 1324b(a)(3) with "
            "programming experience."
        )
        assert "c" not in accepted_slugs(matcher, text)

    def test_c_after_sentence_period_with_space_still_matches(self, matcher):
        slugs = accepted_slugs(matcher, "We ship firmware. C and C++ experience required.")
        assert "c" in slugs
