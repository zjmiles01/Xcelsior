"""The micro-market: 25 synthetic jobs whose every statistic is computed
by hand in this file's comments and asserted in test_market_invariants.

This is the known-truth layer of the test strategy (§19): the likeliest
production failure is not a crash but a dashboard confidently showing a
wrong number. These jobs run through the real schema, real query builder,
and real aggregation SQL.

Ground truth (active jobs = 23; 2 expired rows are invisible everywhere):

  #  title-family        city          techs (level)                salary(mid)   arr    level
  1-6  backend (x6)      San Francisco python(req)+postgresql(req)  200k(1-4 only) hybrid senior
  7-8  backend (x2)      Oakland       python(req)                  150k          onsite mid
  9-10 backend (x2)      San Jose      python(pref)                 —             onsite mid
  11-2 backend (x2)      SF+NYC multi  go(req)                      250k          remote senior
  13-7 frontend (x5)     New York      react(req)+typescript(ment)  120k          hybrid entry
  18-20 ml (x3)          (remote,no geo) python(req)+pytorch(req)   300k          remote staff_plus
  21-23 unresolved (x3)  Denver        (none)                       —             None   None
  24   backend expired   San Francisco python(req)                  999k          onsite senior
  25   frontend expired  New York      react(req)                   —             onsite entry

Hand-computed invariants used by the tests:
  national analyzed = 23
  python jobs = 6+2+2+3 = 13  (share 13/23)
  python required_count = 6+2+3 = 11 (jobs 9-10 are preferred)
  go = 2, react = 5, typescript = 5, postgresql = 6, pytorch = 3
  salary disclosed = 4+2+2+5+3 = 16
    midpoints: 200k x4, 150k x2, 250k x2, 120k x5, 300k x3
    sorted: 120,120,120,120,120,150,150,200,200,200,200,250,250,300,300,300
    median = (200+200)/2 = 200000
  arrangements: hybrid 11, onsite 4, remote 5, unspecified 3
  levels: senior 8, mid 4, entry 5, staff_plus 3, unspecified 3
  employment types: internship 2 (#13-14), contract 1 (#9),
    full_time 17, unspecified 3 (#21-23, NULL — never extracted)
  SF 10mi = SF-only jobs + multi = 6+2 = 8 (Oakland ~8mi -> in 10mi? see
    note below), SF 50mi adds San Jose. Oakland-SF is ~8 miles: included
    at 10. So SF10 = 6 SF + 2 Oakland + 2 multi = 10; SF50 = +2 SJ = 12.
  NYC 10mi = 5 frontend + 2 multi = 7.

Cross-source duplicates (M5): a second source ("micro-agg", aggregator)
carries two copies of postings already above, grouped by the real
`assign_dedupe_groups` run at the end of seeding:
  26  duplicate of #1 via the exact key (same company class, title
      "Job 1", SF) — carries python(req) and a deliberately absurd 400k
      salary so any leak into stats is loud
  27  duplicate of #13 via URL identity (same apply_url, different
      title) — carries react(req) and salary 500k, same tripwire idea
Both point their dedupe_group_id at the original (ats_api beats
aggregator_api), so EVERY number above is unchanged: analyzed stays 23,
python stays 13, salary median stays 200k. Total job rows = 27.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.catalog.models import Company, Job, JobLocation
from app.catalog.taxonomy_models import CanonicalTitle, JobTechnology, Technology
from app.extraction.service import sync_taxonomy
from app.geo.resolver import load_geo_index
from app.ingestion.dedupe import assign_dedupe_groups
from app.ingestion.models import RawPosting, Source

NOW = datetime(2026, 7, 1, tzinfo=UTC)

CITY = {
    "sf": "San Francisco",
    "oakland": "Oakland",
    "sj": "San Jose",
    "nyc": "New York City",
    "denver": "Denver",
}


def _location(kind: str) -> dict:
    geo = load_geo_index()
    lookup = {
        "sf": ("San Francisco", "CA"),
        "oakland": ("Oakland", "CA"),
        "sj": ("San Jose", "CA"),
        "nyc": ("New York City", "NY"),
        "denver": ("Denver", "CO"),
    }
    name, state = lookup[kind]
    city = geo.lookup(name, state)
    assert city is not None
    return {
        "raw_text": city.label,
        "city": city.name,
        "region": city.state,
        "latitude": city.latitude,
        "longitude": city.longitude,
    }


def seed_micro_market(db: Session) -> None:
    sync_taxonomy(db)
    source = Source(name="micro", kind="ats_api", display_policy="full_text")
    agg_source = Source(name="micro-agg", kind="aggregator_api", display_policy="extracted_only")
    company = Company(name="MicroCorp", name_normalized="microcorp")
    db.add_all([source, agg_source, company])
    db.flush()

    tech = {
        t.slug: t.id
        for t in db.query(Technology).filter(
            Technology.slug.in_(["python", "postgresql", "go", "react", "typescript", "pytorch"])
        )
    }
    title = {
        t.slug: t.id
        for t in db.query(CanonicalTitle).filter(
            CanonicalTitle.slug.in_(["backend-engineer", "frontend-engineer",
                                     "machine-learning-engineer"])
        )
    }

    counter = 0

    def job(
        *,
        title_slug: str | None,
        status: str = "active",
        arrangement: str | None,
        level: str | None,
        salary_mid: int | None,
        locations: list[str | dict],
        techs: list[tuple[str, str]],
        from_source: Source | None = None,
        title_text: str | None = None,
        apply_url: str | None = None,
        employment: str | None = "full_time",
    ) -> None:
        nonlocal counter
        counter += 1
        job_source = from_source or source
        # The schema (rightly) refuses jobs without raw provenance; give
        # each synthetic job a synthetic raw posting.
        raw = RawPosting(
            source_id=job_source.id,
            external_id=f"micro-{counter}",
            payload={"synthetic": True},
            content_hash=f"micro-{counter}",
        )
        db.add(raw)
        db.flush()
        j = Job(
            source_id=job_source.id,
            company_id=company.id,
            raw_posting_id=raw.id,
            title_raw=title_text or f"Job {counter}",
            apply_url=apply_url,
            canonical_title_id=title[title_slug] if title_slug else None,
            status=status,
            arrangement=arrangement,
            experience_level=level,
            employment_type=employment,
            salary_annual_min=salary_mid,
            salary_annual_max=salary_mid,
            posted_at=NOW,
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        db.add(j)
        db.flush()
        for loc in locations:
            if isinstance(loc, str):
                db.add(JobLocation(job_id=j.id, **_location(loc)))
            else:
                db.add(JobLocation(job_id=j.id, **loc))
        for slug, req_level in techs:
            db.add(
                JobTechnology(
                    job_id=j.id,
                    technology_id=tech[slug],
                    requirement_level=req_level,
                    confidence=1.0,
                    extractor_version=1,
                    evidence_snippet="synthetic",
                    evidence_start=0,
                )
            )

    be = dict(title_slug="backend-engineer")
    fe = dict(title_slug="frontend-engineer")

    # 1-6: SF backend, python+postgresql required; salary on first four
    for i in range(6):
        job(**be, arrangement="hybrid", level="senior",
            salary_mid=200_000 if i < 4 else None, locations=["sf"],
            techs=[("python", "required"), ("postgresql", "required")])
    # 7-8: Oakland backend
    for _ in range(2):
        job(**be, arrangement="onsite", level="mid", salary_mid=150_000,
            locations=["oakland"], techs=[("python", "required")])
    # 9-10: San Jose backend, python merely preferred (#9 is the contract
    # posting — one non-full-time type that is not an internship)
    for i in range(2):
        job(**be, arrangement="onsite", level="mid", salary_mid=None,
            locations=["sj"], techs=[("python", "preferred")],
            employment="contract" if i == 0 else "full_time")
    # 11-12: multi-location SF+NYC, go required (the count-once probes)
    for _ in range(2):
        job(**be, arrangement="remote", level="senior", salary_mid=250_000,
            locations=["sf", "nyc"], techs=[("go", "required")])
    # 13-17: NYC frontend (#13 gets an apply_url so a URL-rule duplicate
    # can target it below)
    # (#13-14 are the internships: entry-level frontend, the shape a real
    # internship posting takes)
    for i in range(5):
        job(**fe, arrangement="hybrid", level="entry", salary_mid=120_000,
            locations=["nyc"],
            apply_url="https://boards.example.com/microcorp/13" if i == 0 else None,
            techs=[("react", "required"), ("typescript", "mentioned")],
            employment="internship" if i < 2 else "full_time")
    # 18-20: remote ML, no geocodable location
    for _ in range(3):
        job(title_slug="machine-learning-engineer", arrangement="remote",
            level="staff_plus", salary_mid=300_000,
            locations=[{"raw_text": "Remote - US", "is_remote": True}],
            techs=[("python", "required"), ("pytorch", "required")])
    # 21-23: Denver, nothing extracted (denominator jobs) — employment_type
    # stays NULL, the state of every row ingested before employment typing
    # existed and of anything still awaiting extraction
    for _ in range(3):
        job(title_slug=None, arrangement=None, level=None, salary_mid=None,
            locations=["denver"], techs=[], employment=None)
    # 24-25: expired — must be invisible in every number above
    job(**be, status="expired", arrangement="onsite", level="senior",
        salary_mid=999_000, locations=["sf"], techs=[("python", "required")])
    job(**fe, status="expired", arrangement="onsite", level="entry",
        salary_mid=None, locations=["nyc"], techs=[("react", "required")])

    # 26-27: cross-source duplicates from the aggregator source, grouped
    # by the real dedup rules below; absurd salaries are tripwires — if a
    # duplicate ever leaks into stats, the median moves loudly.
    job(**be, from_source=agg_source, title_text="Job 1", arrangement="hybrid",
        level="senior", salary_mid=400_000, locations=["sf"],
        techs=[("python", "required")])
    job(**fe, from_source=agg_source, title_text="Sr Job 13 (via agg)",
        arrangement="hybrid", level="entry", salary_mid=500_000, locations=["nyc"],
        apply_url="https://boards.example.com/microcorp/13?utm_source=agg",
        techs=[("react", "required")])

    db.commit()
    assign_dedupe_groups(db)
