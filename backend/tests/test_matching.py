"""Pure matching-score truth (M9), hand-computed the way the market
invariants are.

Every expected number below is derived by hand in the comments from the
documented scoring rules (weights 0.55 skills / 0.25 title / 0.20
experience; required skills count double; N/A components drop and the rest
renormalise). No value is copied from a first run's output — if the code
disagrees with a comment, the code is wrong.

The taxonomy for these tests is a tiny fixed id map:
  1 python  2 postgresql  3 docker  4 aws  5 kafka  6 terraform  7 rust
Titles: 100 backend-engineer, 101 frontend-engineer, 102 data-scientist.
"""

from datetime import date

from app.profile.matching import (
    CandidateFacts,
    JobFacts,
    JobTech,
    derive_level,
    level_for_years,
    merge_months,
    score_job,
)

TECH = {
    1: ("python", "Python"),
    2: ("postgresql", "PostgreSQL"),
    3: ("docker", "Docker"),
    4: ("aws", "AWS"),
    5: ("kafka", "Kafka"),
    6: ("terraform", "Terraform"),
    7: ("rust", "Rust"),
}


def tech(tid: int, level: str) -> JobTech:
    slug, name = TECH[tid]
    return JobTech(technology_id=tid, slug=slug, name=name, requirement_level=level)


def candidate(**over) -> CandidateFacts:
    base = dict(
        skill_tech_ids=frozenset({1, 2, 3, 4}),  # python, postgresql, docker, aws
        title_ids=frozenset({100}),  # backend-engineer
        level="senior",
        years=6.0,
        degree_level="master",
    )
    base.update(over)
    return CandidateFacts(**base)


# ── derivation helpers ───────────────────────────────────────────────────


def test_level_for_years_ladder():
    assert level_for_years(0) == "entry"
    assert level_for_years(1.9) == "entry"
    assert level_for_years(2) == "mid"
    assert level_for_years(5) == "senior"
    assert level_for_years(8) == "staff_plus"
    assert level_for_years(20) == "staff_plus"


def test_derive_level_prefers_explicit_tokens():
    # Explicit "senior" wins even though 1 year of tenure would say entry.
    assert derive_level(["mid", "senior", "entry"], years=1.0) == "senior"
    # No explicit tokens: fall back to the years ladder.
    assert derive_level([], years=6.0) == "senior"
    # Neither: unknown.
    assert derive_level([], years=None) is None


def test_merge_months_counts_overlap_once():
    # Jan2018–Jan2020 and Jun2019–Jun2021 overlap → merged Jan2018–Jun2021
    # = 41 months; disjoint Jan2022–Jan2023 = 12; total 53.
    intervals = [
        (date(2018, 1, 1), date(2020, 1, 1)),
        (date(2019, 6, 1), date(2021, 6, 1)),
        (date(2022, 1, 1), date(2023, 1, 1)),
    ]
    assert merge_months(intervals) == 53


# ── strong end-to-end match (all three components apply) ─────────────────


def test_strong_match_scores_and_explains():
    """Job A: backend-engineer(100), senior, required python/postgresql/kafka,
    preferred docker/terraform, mentioned aws.

    Candidate has python, postgresql, docker, aws.
      skills: denom = 2*3required + 2preferred = 8; num = 2*2 + 1 = 5 → 0.625
      title: 100 in {100} → 1.0
      experience: senior vs senior → meets → 1.0
      all apply → overall = 100*(0.55*0.625 + 0.25 + 0.20) = 79.375 → 79
    """
    job = JobFacts(
        job_id=1,
        canonical_title_id=100,
        canonical_title_name="Backend Engineer",
        experience_level="senior",
        years_of_experience=None,
        technologies=(
            tech(1, "required"),
            tech(2, "required"),
            tech(5, "required"),
            tech(3, "preferred"),
            tech(6, "preferred"),
            tech(4, "mentioned"),
        ),
    )
    result = score_job(candidate(), job)
    assert result is not None
    assert result.score == 79

    comp = {c.key: c for c in result.components}
    assert comp["skills"].score == 0.625
    assert comp["title"].score == 1.0
    assert comp["experience"].score == 1.0
    assert all(c.applicable for c in result.components)
    # Contributions sum (within rounding) to the overall score.
    assert round(sum(c.contribution for c in result.components)) == 79

    # Matched: required by name (PostgreSQL, Python), then preferred Docker,
    # then mentioned AWS. Missing (required/preferred gaps): Kafka, Terraform.
    assert [t.slug for t in result.matched_skills] == ["postgresql", "python", "docker", "aws"]
    assert [t.slug for t in result.missing_skills] == ["kafka", "terraform"]
    assert result.title_matched is True
    assert result.experience.verdict == "meets"

    joined = " | ".join(result.reasons)
    assert "Matches 2 of 3 required skills" in joined
    assert "Missing 1 required skill(s): Kafka" in joined
    assert "Backend Engineer" in joined
    assert "meets the senior requirement" in joined


# ── title differs, experience N/A → renormalised over two components ─────


def test_partial_match_renormalises_when_experience_missing():
    """Job B: frontend-engineer(101), no level/years, required python only.

      skills: denom 2, num 2 → 1.0 (candidate has python)
      title: 101 not in {100} → 0.0
      experience: no level, no years → N/A (dropped)
      applicable weight = 0.55 + 0.25 = 0.80
      overall = 100*(0.55*1.0 + 0.25*0.0)/0.80 = 68.75 → 69
    """
    job = JobFacts(
        job_id=2,
        canonical_title_id=101,
        canonical_title_name="Frontend Engineer",
        experience_level=None,
        years_of_experience=None,
        technologies=(tech(1, "required"),),
    )
    result = score_job(candidate(), job)
    assert result is not None
    assert result.score == 69
    comp = {c.key: c for c in result.components}
    assert comp["skills"].score == 1.0
    assert comp["title"].score == 0.0
    assert comp["experience"].applicable is False
    assert comp["experience"].score is None
    assert result.title_matched is False
    assert result.experience.verdict == "unspecified"


# ── no shared signal → not a match at all ────────────────────────────────


def test_zero_overlap_is_not_a_match():
    """Job C: data-scientist(102), required rust (candidate lacks), no title
    overlap → no matched skill and no title match → None."""
    job = JobFacts(
        job_id=3,
        canonical_title_id=102,
        canonical_title_name="Data Scientist",
        experience_level="mid",
        years_of_experience=None,
        technologies=(tech(7, "required"),),
    )
    assert score_job(candidate(), job) is None


# ── title-only signal (no skills overlap) still matches ──────────────────


def test_title_only_signal_matches():
    """Job D: backend-engineer(100), required rust (candidate lacks),
    entry level.

      skills: denom 2, num 0 → 0.0 (matched empty, missing = [rust])
      title: 100 in {100} → 1.0
      experience: entry(0) vs senior(2) → exceeds → 1.0
      overall = 100*(0.55*0.0 + 0.25*1.0 + 0.20*1.0) = 45
    Signal comes from the title match despite zero skill overlap.
    """
    job = JobFacts(
        job_id=4,
        canonical_title_id=100,
        canonical_title_name="Backend Engineer",
        experience_level="entry",
        years_of_experience=None,
        technologies=(tech(7, "required"),),
    )
    result = score_job(candidate(), job)
    assert result is not None
    assert result.score == 45
    assert result.matched_skills == ()
    assert [t.slug for t in result.missing_skills] == ["rust"]
    assert result.title_matched is True
    assert result.experience.verdict == "exceeds"


# ── seniority shortfall penalty ──────────────────────────────────────────


def test_below_level_is_penalised():
    """Job E: staff_plus(3) vs candidate senior(2), gap -1.
      experience score = 1.0 + 0.34*(-1) = 0.66, verdict below.
      skills: required python → 1.0; title backend → 1.0.
      overall = 100*(0.55*1.0 + 0.25*1.0 + 0.20*0.66) = 93.2 → 93
    """
    job = JobFacts(
        job_id=5,
        canonical_title_id=100,
        canonical_title_name="Backend Engineer",
        experience_level="staff_plus",
        years_of_experience=None,
        technologies=(tech(1, "required"),),
    )
    result = score_job(candidate(), job)
    assert result is not None
    comp = {c.key: c for c in result.components}
    assert comp["experience"].score == 0.66
    assert result.experience.verdict == "below"
    assert result.score == 93


def test_years_fallback_when_no_level():
    """Job with years_of_experience=8, no level; candidate 6 years, no level.
      candidate rank derived from 6y = senior, but the years branch fires
      first because the job has no level: 6/8 = 0.75, verdict below.
    """
    cand = candidate(level=None, years=6.0)
    job = JobFacts(
        job_id=6,
        canonical_title_id=101,
        canonical_title_name="Frontend Engineer",
        experience_level=None,
        years_of_experience=8,
        technologies=(tech(1, "required"),),
    )
    result = score_job(cand, job)
    assert result is not None
    comp = {c.key: c for c in result.components}
    assert comp["experience"].score == 0.75
    assert result.experience.verdict == "below"


def test_experience_unknown_when_profile_has_no_seniority():
    """Job asks a level but the candidate has neither level nor years →
    experience component is N/A (unknown), dropped from the weighting."""
    cand = candidate(level=None, years=None)
    job = JobFacts(
        job_id=7,
        canonical_title_id=100,
        canonical_title_name="Backend Engineer",
        experience_level="senior",
        years_of_experience=None,
        technologies=(tech(1, "required"),),
    )
    result = score_job(cand, job)
    assert result is not None
    comp = {c.key: c for c in result.components}
    assert comp["experience"].applicable is False
    assert result.experience.verdict == "unknown"
    # Only skills(1.0) + title(1.0) apply → renormalised to 100.
    assert result.score == 100
