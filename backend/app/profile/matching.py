"""Explainable resume-to-job matching (M9).

The seam ADR-005 built for: a reviewed candidate profile and an active job
already speak one vocabulary (`profile_skills.technology_id` ↔
`job_technologies.technology_id`; `profile_experiences.canonical_title_id`
↔ `jobs.canonical_title_id`), so matching is a join plus a *deterministic,
inspectable* scoring policy — never an opaque AI number.

Two halves, kept apart on purpose:

- **Pure scoring** (`score_job`, and the component helpers): given
  `CandidateFacts` + `JobFacts`, produce a `JobMatchResult` with an
  integer 0–100 score, the weighted component breakdown that produced it,
  the matched/missing skills, title and experience alignment, and
  human-readable reasons. No database, no clock — every number is
  hand-checkable, and the matching tests assert against hand-computed
  truth the same way the market-invariant suite does.
- **Orchestration** (`compute_matches`, in the service layer) resolves the
  candidate's facts, draws the candidate job pool through the shared
  `job_predicate` (invariant #1 — matching counts jobs the exact way every
  other surface does), scores every job that shares a signal, and ranks.

Scoring is a weighted sum of up to three components — skills (0.55),
title family (0.25), experience level (0.20). A component that cannot
apply to a job (no extracted skills, an unresolved title, an unspecified
seniority) is dropped and the remaining weights are renormalised, so a
candidate is never penalised for a *job's* missing metadata. A job only
becomes a match at all when the candidate shares at least one of its
skills or its title family — a zero-overlap job is not a weak match, it is
not a match.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import Select, func, select, union
from sqlalchemy.orm import Session

from app.catalog.filters import JobFilters
from app.catalog.models import Job
from app.catalog.query import job_predicate, resolve_filters
from app.catalog.schemas import JobLocationOut, SalaryOut
from app.catalog.taxonomy_models import CanonicalTitle, JobTechnology, Technology
from app.profile.models import CandidateProfile
from app.profile.schemas import (
    ExperienceAlignmentOut,
    JobMatchOut,
    MatchJobSummary,
    MatchProfileSummary,
    MatchSkillOut,
    MatchWeights,
    ProfileMatchesResponse,
    ScoreComponentOut,
    TitleAlignmentOut,
)

# Seniority and degree ladders — the only ordinal comparisons in matching.
LEVEL_RANK: dict[str, int] = {"entry": 0, "mid": 1, "senior": 2, "staff_plus": 3}
LEVEL_NAME: dict[int, str] = {v: k for k, v in LEVEL_RANK.items()}
DEGREE_RANK: dict[str, int] = {"associate": 0, "bachelor": 1, "master": 2, "doctorate": 3}

# Component weights. Nominal — actual contribution is renormalised over the
# components that apply to a given job (see `score_job`).
WEIGHT_SKILLS = 0.55
WEIGHT_TITLE = 0.25
WEIGHT_EXPERIENCE = 0.20

# Required skills count double preferred ones in coverage: a role's "must
# have" list is the harder, more meaningful bar than its "nice to have".
REQUIRED_MULTIPLIER = 2

# Each level below what a role asks for costs a third of the experience
# component — three full levels of shortfall zeroes it, not a cliff at one.
LEVEL_GAP_PENALTY = 0.34

# Years-of-experience → seniority, used only when a profile has no explicit
# level tokens to read (bare "Engineer" titles with dated tenure).
_YEARS_TO_LEVEL = ((8, "staff_plus"), (5, "senior"), (2, "mid"), (0, "entry"))

# Presentation order for a job's skills in matched/missing lists.
_REQUIREMENT_ORDER = {"required": 0, "preferred": 1, "mentioned": 2}


@dataclass(frozen=True)
class CandidateFacts:
    """The matchable shape of a reviewed profile. Skills and titles are the
    taxonomy ids that join job facts; level/years/degree are the derived
    seniority and education signals."""

    skill_tech_ids: frozenset[int]
    title_ids: frozenset[int]
    level: str | None  # entry | mid | senior | staff_plus (the profile's highest)
    years: float | None  # total years of experience, overlap-merged
    degree_level: str | None  # associate | bachelor | master | doctorate (highest)


@dataclass(frozen=True)
class JobTech:
    technology_id: int
    slug: str
    name: str
    requirement_level: str  # required | preferred | mentioned


@dataclass(frozen=True)
class JobFacts:
    job_id: int
    canonical_title_id: int | None
    canonical_title_name: str | None
    experience_level: str | None  # entry | mid | senior | staff_plus
    years_of_experience: int | None
    technologies: tuple[JobTech, ...]
    canonical_title_slug: str | None = None  # only used to link the match card


@dataclass(frozen=True)
class ScoreComponent:
    key: str  # skills | title | experience
    label: str
    weight: float  # nominal weight
    score: float | None  # 0..1, or None when the component does not apply
    applicable: bool
    contribution: float  # this component's share of the final 0..100 score
    detail: str  # one-line human explanation


@dataclass(frozen=True)
class ExperienceAlignment:
    verdict: str  # meets | exceeds | below | unknown | unspecified
    candidate_level: str | None
    candidate_years: float | None
    job_level: str | None
    job_years: int | None


@dataclass(frozen=True)
class JobMatchResult:
    job_id: int
    score: int  # 0..100
    components: tuple[ScoreComponent, ...]
    matched_skills: tuple[JobTech, ...]  # job skills the candidate has
    missing_skills: tuple[JobTech, ...]  # required/preferred gaps
    title_matched: bool | None  # None when title alignment does not apply
    experience: ExperienceAlignment
    reasons: tuple[str, ...]


# ── Candidate-fact derivation ───────────────────────────────────────────


def derive_level(explicit_levels: list[str], years: float | None) -> str | None:
    """Highest explicit seniority token, else one derived from tenure, else
    None. Explicit wins: a resume that says 'Senior' outranks year-counting."""
    ranks = [LEVEL_RANK[level] for level in explicit_levels if level in LEVEL_RANK]
    if ranks:
        return LEVEL_NAME[max(ranks)]
    return level_for_years(years) if years is not None else None


def level_for_years(years: float) -> str:
    for threshold, level in _YEARS_TO_LEVEL:
        if years >= threshold:
            return level
    return "entry"


def merge_months(intervals: list[tuple[date, date]]) -> int:
    """Total months covered by a set of (start, end) intervals, counting
    overlapping tenure once — two concurrent jobs are not double the
    experience."""
    spans = sorted((s, e) for s, e in intervals if e >= s)
    months = 0
    cur_start: date | None = None
    cur_end: date | None = None
    for start, end in spans:
        if cur_end is None or start > cur_end:
            if cur_start is not None and cur_end is not None:
                months += _months_between(cur_start, cur_end)
            cur_start, cur_end = start, end
        elif end > cur_end:
            cur_end = end
    if cur_start is not None and cur_end is not None:
        months += _months_between(cur_start, cur_end)
    return months


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


# ── Component scoring ────────────────────────────────────────────────────


def _score_skills(
    cand: CandidateFacts, job: JobFacts
) -> tuple[float | None, list[JobTech], list[JobTech]]:
    """Weighted coverage of a job's required+preferred skills, plus the
    matched/missing lists the UI shows. Returns (score|None, matched,
    missing); score is None when the job lists no skills at all."""
    required = [t for t in job.technologies if t.requirement_level == "required"]
    preferred = [t for t in job.technologies if t.requirement_level == "preferred"]
    mentioned = [t for t in job.technologies if t.requirement_level == "mentioned"]

    def has(t: JobTech) -> bool:
        return t.technology_id in cand.skill_tech_ids

    matched = sorted(
        (t for t in job.technologies if has(t)),
        key=lambda t: (_REQUIREMENT_ORDER.get(t.requirement_level, 9), t.name.lower()),
    )
    missing = sorted(
        (t for t in required + preferred if not has(t)),
        key=lambda t: (_REQUIREMENT_ORDER.get(t.requirement_level, 9), t.name.lower()),
    )

    denom = REQUIRED_MULTIPLIER * len(required) + len(preferred)
    if denom:
        num = REQUIRED_MULTIPLIER * sum(has(t) for t in required) + sum(has(t) for t in preferred)
        score: float | None = num / denom
    elif mentioned:
        # No required/preferred bar: fall back to plain coverage of the
        # loosely-mentioned skills, which is all the job gives us.
        score = sum(has(t) for t in mentioned) / len(mentioned)
    else:
        score = None  # a job with no extracted skills cannot score on skills
    return score, matched, missing


def _score_title(cand: CandidateFacts, job: JobFacts) -> float | None:
    """1.0 when a role's canonical family is one the candidate has held,
    0.0 when it differs, None when either side has no canonical title to
    compare (an unresolved posting or a title-less profile)."""
    if job.canonical_title_id is None or not cand.title_ids:
        return None
    return 1.0 if job.canonical_title_id in cand.title_ids else 0.0


def _score_experience(cand: CandidateFacts, job: JobFacts) -> tuple[float | None, str]:
    """Seniority alignment. Prefers the role's level ladder; falls back to a
    years-of-experience comparison; N/A when the role specifies neither or
    the profile has no seniority signal. Returns (score|None, verdict)."""
    if job.experience_level in LEVEL_RANK:
        job_rank = LEVEL_RANK[job.experience_level]
        cand_rank = _candidate_rank(cand)
        if cand_rank is None:
            return None, "unknown"
        gap = cand_rank - job_rank
        if gap > 0:
            return 1.0, "exceeds"
        if gap == 0:
            return 1.0, "meets"
        return max(0.0, 1.0 + LEVEL_GAP_PENALTY * gap), "below"

    if job.years_of_experience is not None:
        if cand.years is None:
            return None, "unknown"
        if cand.years >= job.years_of_experience:
            return 1.0, "exceeds" if cand.years > job.years_of_experience else "meets"
        # Partial credit proportional to how close the tenure is.
        ratio = cand.years / job.years_of_experience if job.years_of_experience else 1.0
        return max(0.0, min(1.0, ratio)), "below"

    return None, "unspecified"


def _candidate_rank(cand: CandidateFacts) -> int | None:
    if cand.level in LEVEL_RANK:
        return LEVEL_RANK[cand.level]
    if cand.years is not None:
        return LEVEL_RANK[level_for_years(cand.years)]
    return None


# ── Assembly ─────────────────────────────────────────────────────────────


def score_job(
    cand: CandidateFacts, job: JobFacts, *, require_signal: bool = True
) -> JobMatchResult | None:
    """Score one job against the candidate. With `require_signal` (the
    default, used by the M9 matcher) a job that shares no signal — no matched
    skill and no title-family match — returns None and must not appear in
    results. The saved-jobs dashboard passes `require_signal=False`: the user
    explicitly saved the job, so it is always explained (even at score 0),
    never silently dropped."""
    skill_score, matched, missing = _score_skills(cand, job)
    title_score = _score_title(cand, job)
    exp_score, exp_verdict = _score_experience(cand, job)

    title_matched = None if title_score is None else title_score == 1.0
    if require_signal and not matched and title_matched is not True:
        return None

    raw = [
        ("skills", "Skills", WEIGHT_SKILLS, skill_score),
        ("title", "Role family", WEIGHT_TITLE, title_score),
        ("experience", "Experience", WEIGHT_EXPERIENCE, exp_score),
    ]
    applicable_weight = sum(w for _, _, w, s in raw if s is not None)

    components: list[ScoreComponent] = []
    weighted_total = 0.0
    for key, label, weight, score in raw:
        applicable = score is not None
        contribution = 0.0
        if applicable and applicable_weight:
            contribution = round(100 * weight * score / applicable_weight, 1)
            weighted_total += weight * score
        components.append(
            ScoreComponent(
                key=key,
                label=label,
                weight=weight,
                score=None if score is None else round(score, 3),
                applicable=applicable,
                contribution=contribution,
                detail=_component_detail(
                    key, score, job, matched, missing, exp_verdict, cand
                ),
            )
        )

    overall = round(100 * weighted_total / applicable_weight) if applicable_weight else 0
    experience = ExperienceAlignment(
        verdict=exp_verdict,
        candidate_level=cand.level,
        candidate_years=cand.years,
        job_level=job.experience_level,
        job_years=job.years_of_experience,
    )
    return JobMatchResult(
        job_id=job.job_id,
        score=overall,
        components=tuple(components),
        matched_skills=tuple(matched),
        missing_skills=tuple(missing),
        title_matched=title_matched,
        experience=experience,
        reasons=_reasons(job, matched, missing, title_matched, exp_verdict),
    )


def _component_detail(
    key: str,
    score: float | None,
    job: JobFacts,
    matched: list[JobTech],
    missing: list[JobTech],
    exp_verdict: str,
    cand: CandidateFacts,
) -> str:
    if key == "skills":
        if score is None:
            return "This posting lists no recognised skills."
        required = [t for t in job.technologies if t.requirement_level == "required"]
        req_matched = sum(1 for t in required if t.technology_id in cand.skill_tech_ids)
        if required:
            return f"You have {req_matched} of {len(required)} required skills."
        return f"You have {len(matched)} of the skills this posting mentions."
    if key == "title":
        if score is None:
            return "No canonical role family to compare."
        if score == 1.0:
            return f"You have held a {job.canonical_title_name} role."
        return f"Your roles differ from {job.canonical_title_name}."
    if key == "experience":
        return _experience_detail(exp_verdict, job)
    return ""


def _experience_detail(verdict: str, job: JobFacts) -> str:
    target = job.experience_level or (
        f"{job.years_of_experience}+ years" if job.years_of_experience is not None else None
    )
    if verdict == "meets":
        return f"Your experience meets the {target} level." if target else "Experience aligned."
    if verdict == "exceeds":
        return f"Your experience exceeds the {target} level." if target else "Experience exceeds."
    if verdict == "below":
        return f"This role targets {target}; your experience is below it."
    if verdict == "unknown":
        return "Not enough experience detail on your profile to compare."
    return "This posting does not specify a seniority level."


def _reasons(
    job: JobFacts,
    matched: list[JobTech],
    missing: list[JobTech],
    title_matched: bool | None,
    exp_verdict: str,
) -> tuple[str, ...]:
    """Short, ranked, human-readable justifications for the score."""
    reasons: list[str] = []

    required = [t for t in job.technologies if t.requirement_level == "required"]
    matched_required = [t for t in matched if t.requirement_level == "required"]
    if required:
        names = ", ".join(t.name for t in matched_required)
        base = f"Matches {len(matched_required)} of {len(required)} required skills"
        reasons.append(f"{base} ({names})" if names else base)
    elif matched:
        names = ", ".join(t.name for t in matched[:4])
        reasons.append(f"Matches skills this posting lists ({names})")

    missing_required = [t for t in missing if t.requirement_level == "required"]
    if missing_required:
        names = ", ".join(t.name for t in missing_required)
        reasons.append(f"Missing {len(missing_required)} required skill(s): {names}")

    if title_matched is True:
        reasons.append(f"Your background includes the {job.canonical_title_name} role")

    exp_line = _experience_reason(exp_verdict, job)
    if exp_line:
        reasons.append(exp_line)
    return tuple(reasons)


def _experience_reason(verdict: str, job: JobFacts) -> str | None:
    target = job.experience_level or (
        f"{job.years_of_experience}+ years" if job.years_of_experience is not None else None
    )
    if not target:
        return None
    if verdict == "meets":
        return f"Your experience meets the {target} requirement"
    if verdict == "exceeds":
        return f"Your experience exceeds the {target} requirement"
    if verdict == "below":
        return f"This role targets {target}, above your current experience"
    return None


# ── Orchestration (DB) ───────────────────────────────────────────────────
#
# The pure functions above never touch the database; everything below draws
# candidate facts and the candidate job pool, scores, and ranks. The job
# pool comes from the shared `job_predicate` (invariant #1) so matching
# counts jobs exactly the way search and analytics do — the same optional
# `JobFilters` scope (location, arrangement, salary floor, …) applies here.


def build_candidate_facts(profile: CandidateProfile, today: date) -> CandidateFacts:
    """Reduce a reviewed profile to the ids and derived signals matching
    joins on. `today` is injected so tenure (hence derived seniority) is
    deterministic in tests."""
    skill_ids = frozenset(
        s.technology_id for s in profile.skills if s.technology_id is not None
    )
    title_ids = frozenset(
        e.canonical_title_id for e in profile.experiences if e.canonical_title_id is not None
    )

    intervals: list[tuple[date, date]] = []
    for exp in profile.experiences:
        if exp.start_date is None:
            continue
        end = exp.end_date or (today if exp.is_current else None)
        if end is None:
            continue
        intervals.append((exp.start_date, end))
    months = merge_months(intervals) if intervals else None
    years = round(months / 12, 1) if months is not None else None

    level = derive_level([e.level for e in profile.experiences if e.level], years)

    degree_ranks = [
        DEGREE_RANK[e.degree_level] for e in profile.education if e.degree_level in DEGREE_RANK
    ]
    degree_level = (
        {v: k for k, v in DEGREE_RANK.items()}[max(degree_ranks)] if degree_ranks else None
    )

    return CandidateFacts(
        skill_tech_ids=skill_ids,
        title_ids=title_ids,
        level=level,
        years=years,
        degree_level=degree_level,
    )


def _signal_pool(pool, skill_ids: frozenset[int], title_ids: frozenset[int]) -> Select | None:
    """A SELECT of pool job ids that share at least one candidate skill or
    the candidate's title family — the only jobs worth scoring. None when
    the candidate has neither matchable skills nor titles."""
    parts: list[Select] = []
    if skill_ids:
        parts.append(
            select(JobTechnology.job_id.label("id"))
            .join(pool, pool.c.id == JobTechnology.job_id)
            .where(JobTechnology.technology_id.in_(skill_ids))
            .distinct()
        )
    if title_ids:
        parts.append(
            select(Job.id.label("id"))
            .join(pool, pool.c.id == Job.id)
            .where(Job.canonical_title_id.in_(title_ids))
        )
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else union(*parts)


def compute_matches(
    db: Session, profile: CandidateProfile, filters: JobFilters, limit: int
) -> ProfileMatchesResponse:
    cand = build_candidate_facts(profile, datetime.now(UTC).date())

    resolved = resolve_filters(db, filters)
    pool = job_predicate(resolved).cte("candidate_jobs")
    total_active = db.scalar(select(func.count()).select_from(pool)) or 0

    summary = _profile_summary(db, profile, cand)
    base = _empty_response(filters, summary, total_active)

    signal = _signal_pool(pool, cand.skill_tech_ids, cand.title_ids)
    if signal is None:
        return base
    signal_cte = signal.cte("signal_jobs")

    facts = _load_job_facts(db, signal_cte)
    results = [r for r in (score_job(cand, job) for job in facts.values()) if r is not None]
    results.sort(
        key=lambda r: (
            -r.score,
            -sum(1 for t in r.matched_skills if t.requirement_level == "required"),
            -len(r.matched_skills),
            r.job_id,
        )
    )

    top = results[:limit]
    summaries = _load_job_summaries(db, [r.job_id for r in top], facts)
    matches = [_to_match_out(r, summaries[r.job_id]) for r in top if r.job_id in summaries]

    base.matched_jobs = len(results)
    base.returned = len(matches)
    base.matches = matches
    return base


def _empty_response(filters, summary, total_active) -> ProfileMatchesResponse:
    return ProfileMatchesResponse(
        profile=summary,
        filters=filters,
        weights=MatchWeights(
            skills=WEIGHT_SKILLS, title=WEIGHT_TITLE, experience=WEIGHT_EXPERIENCE
        ),
        total_active_jobs=total_active,
        matched_jobs=0,
        returned=0,
        matches=[],
        computed_at=datetime.now(UTC),
    )


def _profile_summary(
    db: Session, profile: CandidateProfile, cand: CandidateFacts
) -> MatchProfileSummary:
    families = (
        list(
            db.scalars(
                select(CanonicalTitle.name)
                .where(CanonicalTitle.id.in_(cand.title_ids))
                .order_by(CanonicalTitle.name)
            ).all()
        )
        if cand.title_ids
        else []
    )
    return MatchProfileSummary(
        id=profile.id,
        full_name=profile.full_name,
        reviewed_at=profile.reviewed_at,
        matched_skill_count=len(cand.skill_tech_ids),
        unmapped_skill_count=sum(1 for s in profile.skills if s.technology_id is None),
        title_families=families,
        experience_level=cand.level,
        years_experience=cand.years,
        highest_degree=cand.degree_level,
    )


def _load_job_facts(db: Session, signal_cte) -> dict[int, JobFacts]:
    """Build JobFacts for every signal job in two set-based queries: the
    core fields, then all their technologies (a job's *whole* skill list is
    needed to score coverage, not just the matched subset)."""
    core = db.execute(
        select(
            Job.id,
            Job.canonical_title_id,
            CanonicalTitle.name,
            CanonicalTitle.slug,
            Job.experience_level,
            Job.years_of_experience,
        )
        .join(signal_cte, signal_cte.c.id == Job.id)
        .outerjoin(CanonicalTitle, CanonicalTitle.id == Job.canonical_title_id)
    ).all()

    tech_rows = db.execute(
        select(
            JobTechnology.job_id,
            Technology.id,
            Technology.slug,
            Technology.name,
            JobTechnology.requirement_level,
        )
        .join(signal_cte, signal_cte.c.id == JobTechnology.job_id)
        .join(Technology, Technology.id == JobTechnology.technology_id)
    ).all()

    return _assemble_job_facts(core, tech_rows)


def load_job_facts_by_ids(db: Session, job_ids: list[int]) -> dict[int, JobFacts]:
    """JobFacts for an explicit id list (the saved-jobs dashboard, where the
    pool is the user's saved edges rather than a predicate-drawn set). Same
    two-query shape as `_load_job_facts`."""
    if not job_ids:
        return {}
    core = db.execute(
        select(
            Job.id,
            Job.canonical_title_id,
            CanonicalTitle.name,
            CanonicalTitle.slug,
            Job.experience_level,
            Job.years_of_experience,
        )
        .outerjoin(CanonicalTitle, CanonicalTitle.id == Job.canonical_title_id)
        .where(Job.id.in_(job_ids))
    ).all()
    tech_rows = db.execute(
        select(
            JobTechnology.job_id,
            Technology.id,
            Technology.slug,
            Technology.name,
            JobTechnology.requirement_level,
        )
        .join(Technology, Technology.id == JobTechnology.technology_id)
        .where(JobTechnology.job_id.in_(job_ids))
    ).all()
    return _assemble_job_facts(core, tech_rows)


def _assemble_job_facts(core, tech_rows) -> dict[int, JobFacts]:
    techs_by_job: dict[int, list[JobTech]] = {}
    for job_id, tech_id, slug, name, requirement_level in tech_rows:
        techs_by_job.setdefault(job_id, []).append(
            JobTech(
                technology_id=tech_id,
                slug=slug,
                name=name,
                requirement_level=requirement_level,
            )
        )

    facts: dict[int, JobFacts] = {}
    for job_id, title_id, title_name, title_slug, level, yoe in core:
        facts[job_id] = JobFacts(
            job_id=job_id,
            canonical_title_id=title_id,
            canonical_title_name=title_name,
            canonical_title_slug=title_slug,
            experience_level=level,
            years_of_experience=yoe,
            technologies=tuple(techs_by_job.get(job_id, ())),
        )
    return facts


def _load_job_summaries(
    db: Session, job_ids: list[int], facts: dict[int, JobFacts]
) -> dict[int, MatchJobSummary]:
    if not job_ids:
        return {}
    jobs = db.scalars(select(Job).where(Job.id.in_(job_ids))).all()
    summaries: dict[int, MatchJobSummary] = {}
    for job in jobs:
        fact = facts.get(job.id)
        summaries[job.id] = MatchJobSummary(
            id=job.id,
            title_raw=job.title_raw,
            canonical_title=fact.canonical_title_name if fact else None,
            canonical_title_slug=fact.canonical_title_slug if fact else None,
            company_name=job.company.name,
            locations=[JobLocationOut.model_validate(loc) for loc in job.locations],
            arrangement=job.arrangement,
            experience_level=job.experience_level,
            salary=SalaryOut(
                min_amount=job.salary_min,
                max_amount=job.salary_max,
                currency=job.salary_currency,
                period=job.salary_period,
                annual_min=job.salary_annual_min,
                annual_max=job.salary_annual_max,
            ),
            posted_at=job.posted_at,
            apply_url=job.apply_url,
        )
    return summaries


def _to_match_out(result: JobMatchResult, job: MatchJobSummary) -> JobMatchOut:
    return JobMatchOut(
        job=job,
        score=result.score,
        components=[
            ScoreComponentOut(
                key=c.key,
                label=c.label,
                weight=c.weight,
                score=c.score,
                applicable=c.applicable,
                contribution=c.contribution,
                detail=c.detail,
            )
            for c in result.components
        ],
        matched_skills=[_skill_out(t) for t in result.matched_skills],
        missing_skills=[_skill_out(t) for t in result.missing_skills],
        title=TitleAlignmentOut(
            matched=result.title_matched,
            job_title=job.canonical_title,
            job_title_slug=job.canonical_title_slug,
        ),
        experience=ExperienceAlignmentOut(
            verdict=result.experience.verdict,
            candidate_level=result.experience.candidate_level,
            candidate_years=result.experience.candidate_years,
            job_level=result.experience.job_level,
            job_years=result.experience.job_years,
        ),
        reasons=list(result.reasons),
    )


def _skill_out(t: JobTech) -> MatchSkillOut:
    return MatchSkillOut(slug=t.slug, name=t.name, requirement_level=t.requirement_level)
