"""Skill detail: one technology's market position inside a scope.

Every count resolves through the shared predicate (the skill page's
"N jobs" must equal the search result it links to), and the co-occurrence
list is conditioned honestly: a pairing is only shown when it beats the
technology's base rate in the same scope by the lift floor — "Python jobs
mention AWS" is not information if every job in scope mentions AWS.

Salary delta is measured against the fixed national all-jobs baseline
(not the scope), so "+$18k vs national median" means the same thing on
every skill page.
"""

import hashlib
import json
import re
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.analytics.models import NATIONAL, AnalysisCache, MarketSnapshot
from app.analytics.schemas import (
    CoOccurrenceStat,
    DistributionBucket,
    SkillDetailResponse,
    SkillHeader,
    SkillSalary,
    SkillTrend,
    TrendPoint,
)
from app.analytics.service import MIN_SAMPLE_SIZE, distribution, get_data_version
from app.catalog.filters import JobFilters
from app.catalog.models import Job
from app.catalog.query import job_predicate, resolve_filters
from app.catalog.taxonomy_models import JobTechnology, Technology, TechnologyAlias

CO_OCCURRENCE_LIFT_FLOOR = 1.3
MIN_CO_OCCURRENCE = 3
TOP_CO_OCCURRING = 12
MIN_TREND_DAYS = 7


def canonical_slug_for_alias(db: Session, requested: str) -> str | None:
    """Map an alias-shaped slug ("golang", "react-js") to its canonical
    technology slug, for 301 redirects. None if nothing matches."""
    wanted = _slugify(requested)
    rows = db.execute(
        select(TechnologyAlias.alias, Technology.slug)
        .join(Technology, Technology.id == TechnologyAlias.technology_id)
        .order_by(TechnologyAlias.id)
    ).all()
    for alias, slug in rows:
        if _slugify(alias) == wanted:
            return slug
    return None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def scope_without(tech: Technology, filters: JobFilters) -> JobFilters:
    """The skill page's scope: the same filters with the skill itself
    removed, so the share denominator is the market, not a tautology."""
    if tech.slug not in filters.technologies:
        return filters
    remaining = tuple(t for t in filters.technologies if t != tech.slug)
    return filters.model_copy(update={"technologies": remaining})


def skill_cache_key(slug: str, scope: JobFilters) -> str:
    payload = json.dumps(
        {"skill": slug, "filters": scope.canonical_dict()}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def get_skill_detail(db: Session, tech: Technology, scope: JobFilters) -> SkillDetailResponse:
    """Read-through cache, same contract as get_analysis: entries are
    exactly correct until the nightly pipeline truncates the table."""
    key = skill_cache_key(tech.slug, scope)
    cached = db.get(AnalysisCache, key)
    if cached is not None:
        return SkillDetailResponse.model_validate(cached.payload)

    response = compute_skill_detail(db, tech, scope)
    stmt = pg_insert(AnalysisCache).values(
        cache_key=key,
        filters={"skill": tech.slug, **scope.canonical_dict()},
        payload=response.model_dump(mode="json"),
        computed_at=response.computed_at,
    )
    db.execute(stmt.on_conflict_do_nothing(index_elements=["cache_key"]))
    db.commit()
    return response


def compute_skill_detail(db: Session, tech: Technology, scope: JobFilters) -> SkillDetailResponse:
    resolved_scope = resolve_filters(db, scope)
    scope_jobs = job_predicate(resolved_scope).cte("scope_jobs")
    analyzed = db.scalar(select(func.count()).select_from(scope_jobs)) or 0

    with_tech = scope.model_copy(
        update={"technologies": tuple(sorted((*scope.technologies, tech.slug)))}
    )
    skill_jobs = job_predicate(resolve_filters(db, with_tech)).cte("skill_jobs")
    jobs_with_tech = db.scalar(select(func.count()).select_from(skill_jobs)) or 0

    header = SkillHeader(
        slug=tech.slug,
        name=tech.name,
        category=tech.category,
        analyzed_jobs=analyzed,
        jobs_with_tech=jobs_with_tech,
        share=jobs_with_tech / analyzed if analyzed else 0.0,
        low_confidence=jobs_with_tech < MIN_SAMPLE_SIZE,
        min_sample_size=MIN_SAMPLE_SIZE,
    )

    return SkillDetailResponse(
        filters=scope,
        header=header,
        requirement_levels=_requirement_levels(db, skill_jobs, tech, jobs_with_tech),
        arrangements=distribution(db, skill_jobs, Job.arrangement, jobs_with_tech),
        experience_levels=distribution(db, skill_jobs, Job.experience_level, jobs_with_tech),
        co_occurring=_co_occurring(db, scope_jobs, skill_jobs, tech, analyzed, jobs_with_tech),
        salary=_salary(db, skill_jobs),
        trend=_trend(db, tech, resolved_scope),
        computed_at=datetime.now(UTC),
        data_version=get_data_version(db),
    )


def _requirement_levels(db: Session, skill_jobs, tech: Technology, total: int):
    rows = db.execute(
        select(JobTechnology.requirement_level, func.count().label("count"))
        .select_from(skill_jobs)
        .join(JobTechnology, JobTechnology.job_id == skill_jobs.c.id)
        .where(JobTechnology.technology_id == tech.id)
        .group_by(JobTechnology.requirement_level)
        .order_by(func.count().desc())
    ).all()
    return [
        DistributionBucket(value=v, count=c, share=c / total if total else 0.0) for v, c in rows
    ]


def _co_occurring(
    db: Session, scope_jobs, skill_jobs, tech: Technology, analyzed: int, jobs_with_tech: int
) -> list[CoOccurrenceStat]:
    if not jobs_with_tech or not analyzed:
        return []

    baseline_rows = db.execute(
        select(JobTechnology.technology_id, func.count(JobTechnology.job_id.distinct()))
        .select_from(scope_jobs)
        .join(JobTechnology, JobTechnology.job_id == scope_jobs.c.id)
        .group_by(JobTechnology.technology_id)
    ).all()
    baseline = dict(baseline_rows)

    rows = db.execute(
        select(
            Technology.id,
            Technology.slug,
            Technology.name,
            Technology.category,
            func.count(JobTechnology.job_id.distinct()).label("count"),
        )
        .select_from(skill_jobs)
        .join(JobTechnology, JobTechnology.job_id == skill_jobs.c.id)
        .join(Technology, Technology.id == JobTechnology.technology_id)
        .where(JobTechnology.technology_id != tech.id)
        .group_by(Technology.id, Technology.slug, Technology.name, Technology.category)
    ).all()

    stats = []
    for tech_id, slug, name, category, count in rows:
        if count < MIN_CO_OCCURRENCE:
            continue
        share_given = count / jobs_with_tech
        baseline_share = baseline.get(tech_id, 0) / analyzed
        if baseline_share == 0:
            continue  # co-occurrence rows imply a nonzero baseline; belt and braces
        lift = share_given / baseline_share
        if lift < CO_OCCURRENCE_LIFT_FLOOR:
            continue
        stats.append(
            CoOccurrenceStat(
                slug=slug,
                name=name,
                category=category,
                count=count,
                share_given_tech=share_given,
                baseline_share=baseline_share,
                lift=lift,
            )
        )
    stats.sort(key=lambda s: (-s.share_given_tech, s.name))
    return stats[:TOP_CO_OCCURRING]


def _salary(db: Session, skill_jobs) -> SkillSalary:
    def percentiles(matching) -> tuple[int, int | None, int | None, int | None]:
        midpoint = (Job.salary_annual_min + Job.salary_annual_max) / 2
        row = db.execute(
            select(
                func.count(),
                func.percentile_cont(0.25).within_group(midpoint),
                func.percentile_cont(0.5).within_group(midpoint),
                func.percentile_cont(0.75).within_group(midpoint),
            )
            .select_from(matching)
            .join(Job, Job.id == matching.c.id)
            .where(Job.salary_annual_min.is_not(None))
        ).one()
        return (
            row[0] or 0,
            round(row[1]) if row[1] is not None else None,
            round(row[2]) if row[2] is not None else None,
            round(row[3]) if row[3] is not None else None,
        )

    disclosed, p25, median, p75 = percentiles(skill_jobs)
    national_jobs = job_predicate(resolve_filters(db, JobFilters())).cte("national_jobs")
    national_disclosed, _, national_median, _ = percentiles(national_jobs)

    return SkillSalary(
        disclosed_count=disclosed,
        p25=p25,
        median=median,
        p75=p75,
        national_median=national_median,
        national_disclosed_count=national_disclosed,
        delta_vs_national=(
            median - national_median if median is not None and national_median is not None else None
        ),
    )


def _trend(db: Session, tech: Technology, resolved_scope) -> SkillTrend:
    """Snapshot series at the scope's geo bucket, falling back to the
    national series (labeled as such) when the scope isn't a snapshotted
    metro — a sparse metro series would look like a market collapse."""

    def series(geo_slug: str) -> list[TrendPoint]:
        title_id = resolved_scope.title_id
        stmt = (
            select(MarketSnapshot.snapshot_date, MarketSnapshot.job_count)
            .where(
                MarketSnapshot.technology_id == tech.id,
                MarketSnapshot.geo_slug == geo_slug,
                MarketSnapshot.canonical_title_id.is_(None)
                if title_id is None
                else MarketSnapshot.canonical_title_id == title_id,
            )
            .order_by(MarketSnapshot.snapshot_date)
        )
        return [TrendPoint(snapshot_date=d, job_count=c) for d, c in db.execute(stmt).all()]

    geo_slug = resolved_scope.filters.location or NATIONAL
    points = series(geo_slug)
    if not points and geo_slug != NATIONAL:
        geo_slug = NATIONAL
        points = series(geo_slug)

    return SkillTrend(
        status="ok" if len(points) >= MIN_TREND_DAYS else "collecting_history",
        days_observed=len(points),
        min_days=MIN_TREND_DAYS,
        geo_slug=geo_slug,
        points=points,
    )
