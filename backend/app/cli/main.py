from pathlib import Path

import typer

from app.core.logging import configure_logging

cli = typer.Typer(help="Xcelsior data pipeline commands.")

review = typer.Typer(
    help=(
        "Curate the extraction review queue (unresolved titles, doubt-band "
        "technology matches). Dispositions are bookkeeping only: fixing an "
        "item means editing data/taxonomy/*.yaml, then load-taxonomy and "
        "re-extraction — see 'xcelsior review show' for the loop."
    )
)
cli.add_typer(review, name="review")

DEFAULT_SEED_FILE = Path(__file__).resolve().parents[3] / "data" / "seed_companies.csv"


@cli.callback()
def _setup() -> None:
    import app.models  # noqa: F401  (complete ORM metadata before any DB use)

    configure_logging()


@cli.command()
def seed(seed_file: Path = DEFAULT_SEED_FILE) -> None:
    """Sync the versioned company seed list into the database."""
    from app.core.db import SessionLocal
    from app.ingestion.service import seed_companies

    with SessionLocal() as db:
        count = seed_companies(db, seed_file)
    typer.echo(f"Synced {count} companies from {seed_file}")


@cli.command()
def ingest(
    source: str | None = typer.Option(
        None, help="Only this source; default is every registered, enabled source."
    ),
    limit_companies: int | None = typer.Option(None, help="Only fetch the first N companies."),
) -> None:
    """Fetch postings and upsert raw postings + jobs, one run per source."""
    from app.core.db import SessionLocal
    from app.ingestion.service import ingest_all, ingest_source

    with SessionLocal() as db:
        if source is not None:
            runs = {source: ingest_source(db, source_name=source, limit_companies=limit_companies)}
        else:
            runs = ingest_all(db, limit_companies=limit_companies)
    for name, run in runs.items():
        typer.echo(
            f"{name}: fetched={run.postings_fetched} new={run.postings_new} "
            f"updated={run.postings_updated} errors={run.errors} status={run.status}"
        )


@cli.command()
def expire(
    grace_days: int | None = typer.Option(
        None, help="Days a posting may be unseen before expiring (default: service constant)."
    ),
) -> None:
    """Expire jobs whose postings stopped appearing on their boards."""
    from app.core.db import SessionLocal
    from app.ingestion.service import EXPIRY_GRACE_DAYS, expire_stale_jobs

    with SessionLocal() as db:
        expired = expire_stale_jobs(db, grace_days=grace_days or EXPIRY_GRACE_DAYS)
    if not expired:
        typer.echo("no sources eligible for expiry")
    for name, count in expired.items():
        typer.echo(f"{name}: expired={count}")


@cli.command()
def load_taxonomy() -> None:
    """Sync the versioned taxonomy files into the database."""
    from app.core.db import SessionLocal
    from app.extraction.service import sync_taxonomy

    with SessionLocal() as db:
        techs, titles = sync_taxonomy(db)
    typer.echo(f"Synced {techs} technologies and {titles} canonical titles")


@cli.command()
def extract(
    limit: int | None = typer.Option(None, help="Only process the first N pending jobs."),
) -> None:
    """Run the extraction pipeline over jobs pending (re-)extraction."""
    from app.core.db import SessionLocal
    from app.extraction.service import extract_pending

    with SessionLocal() as db:
        stats = extract_pending(db, limit=limit)
    typer.echo(
        f"processed={stats['processed']} with_technologies={stats['with_technologies']} "
        f"titles_resolved={stats['titles_resolved']} salaries_new={stats['salaries_new']}"
    )


@cli.command()
def geocode(
    redo: bool = typer.Option(False, help="Re-resolve all locations, not just unresolved ones."),
) -> None:
    """Resolve job location strings to canonical cities with coordinates."""
    from app.catalog.geocoding import geocode_locations
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        result = geocode_locations(db, redo=redo)
    attempted = result.get("attempted", 0)
    resolved = result.get("resolved", 0)
    rate = resolved / attempted if attempted else 0.0
    typer.echo(f"attempted={attempted} resolved={resolved} rate={rate:.1%}")


@cli.command()
def dedupe() -> None:
    """Recompute cross-source dedupe groups (idempotent; run after geocode)."""
    from app.core.db import SessionLocal
    from app.ingestion.dedupe import assign_dedupe_groups

    with SessionLocal() as db:
        stats = assign_dedupe_groups(db)
    typer.echo(
        f"groups={stats['groups']} grouped_jobs={stats['grouped_jobs']} "
        f"changed={stats['changed']}"
    )


@cli.command()
def snapshot() -> None:
    """Capture today's market snapshot rows (idempotent per day)."""
    from app.analytics.snapshots import capture_snapshot
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        result = capture_snapshot(db)
    typer.echo(
        f"buckets={result['buckets']} rows={result['rows']} active_jobs={result['active_jobs']}"
    )


@cli.command()
def bump_data_version() -> None:
    """Pipeline's final step: truncate the analysis cache and version the data.

    Everything cached before this instant described the previous corpus;
    one command keeps 'truncate' and 'new version' atomic so ETags and
    cache entries can never disagree about which data they describe.
    """
    from app.analytics.service import bump_data_version as _bump
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        version = _bump(db)
    typer.echo(f"data_version={version} (analysis cache truncated)")


@cli.command()
def gold_eval(
    min_precision: float = typer.Option(0.90, help="Fail below this skills precision."),
    min_recall: float = typer.Option(0.80, help="Fail below this skills recall."),
) -> None:
    """Evaluate the extractor against the labeled gold set; non-zero exit on regression."""
    from app.extraction.evaluation import evaluate_gold_set, format_report

    report = evaluate_gold_set()
    typer.echo(format_report(report))
    if report.skills_precision < min_precision or report.skills_recall < min_recall:
        raise typer.Exit(code=1)


@cli.command()
def stats() -> None:
    """Extraction health: title resolution rate, review queue, location strings."""
    from app.core.db import SessionLocal
    from app.extraction.service import location_string_report, unresolved_title_stats

    with SessionLocal() as db:
        title_stats = unresolved_title_stats(db)
        locations = location_string_report(db, limit=25)

    typer.echo(
        f"active_jobs={title_stats['active_jobs']} "
        f"titles_resolved={title_stats['titles_resolved']} "
        f"resolution_rate={title_stats['resolution_rate']:.1%}"
    )
    typer.echo("\nTop unresolved titles:")
    for value, count in title_stats["top_unresolved"]:
        typer.echo(f"  {count:5d}  {value}")
    typer.echo("\nTop location strings:")
    for text, count in locations:
        typer.echo(f"  {count:5d}  {text}")


@review.command("list")
def review_list(
    kind: str | None = typer.Option(None, help="title | technology (default: both)."),
    status: str = typer.Option("pending", help="pending | resolved | dismissed."),
    limit: int = typer.Option(25, help="Rows to show, most-occurring first."),
) -> None:
    """Queue summary plus the highest-impact items awaiting curation."""
    from app.core.db import SessionLocal
    from app.extraction.review import list_review_items, review_summary

    with SessionLocal() as db:
        summary = review_summary(db)
        items = list_review_items(db, kind=kind, status=status, limit=limit)

    for k, counts in summary.items():
        typer.echo(
            f"{k}: pending={counts['pending']} resolved={counts['resolved']} "
            f"dismissed={counts['dismissed']}"
        )
    if not items:
        typer.echo(f"\nno {status} items" + (f" of kind {kind}" if kind else ""))
        return
    typer.echo(f"\n{'id':>6}  {'occurs':>6}  {'kind':<10}  value")
    for item in items:
        typer.echo(f"{item.id:>6}  {item.occurrences:>6}  {item.kind:<10}  {item.value}")


@review.command("show")
def review_show(item_id: int) -> None:
    """One item in full: evidence context, example job, and the curation loop."""
    from app.catalog.models import Job
    from app.core.db import SessionLocal
    from app.extraction.review import get_review_item

    with SessionLocal() as db:
        item = get_review_item(db, item_id)
        job = db.get(Job, item.example_job_id) if item.example_job_id else None
        typer.echo(f"id:          {item.id}")
        typer.echo(f"kind:        {item.kind}")
        typer.echo(f"value:       {item.value}")
        typer.echo(f"status:      {item.status}")
        typer.echo(f"occurrences: {item.occurrences}")
        seen = f"{item.first_seen_at:%Y-%m-%d} .. {item.last_seen_at:%Y-%m-%d}"
        typer.echo(f"seen:        {seen}")
        if item.example_context:
            typer.echo(f"context:     {item.example_context}")
        if job:
            example = f"#{job.id} {job.title_raw!r} ({job.company.name}, {job.status})"
            typer.echo(f"example job: {example}")
    typer.echo(
        "\nto fix: edit data/taxonomy/*.yaml -> xcelsior load-taxonomy ->\n"
        "        re-extract (titles: xcelsior review requeue-titles + extract;\n"
        "        technologies: bump EXTRACTOR_VERSION), then resolve;\n"
        "        dismiss if out of scope"
    )


@review.command("resolve")
def review_resolve(item_ids: list[int]) -> None:
    """Mark items resolved — record that their taxonomy fix has landed."""
    from app.core.db import SessionLocal
    from app.extraction.review import set_review_status

    with SessionLocal() as db:
        changed = set_review_status(db, item_ids, "resolved")
    typer.echo(f"resolved {changed} item(s)")


@review.command("dismiss")
def review_dismiss(item_ids: list[int]) -> None:
    """Mark items dismissed — out of scope (e.g. non-engineering titles)."""
    from app.core.db import SessionLocal
    from app.extraction.review import set_review_status

    with SessionLocal() as db:
        changed = set_review_status(db, item_ids, "dismissed")
    typer.echo(f"dismissed {changed} item(s)")


@review.command("requeue-titles")
def review_requeue_titles() -> None:
    """Re-queue active jobs with unresolved titles for the next extract run.

    Run after growing data/taxonomy/titles.yaml and load-taxonomy, then
    'xcelsior extract' (and the usual snapshot + bump-data-version) to
    make the new aliases real in the dashboard.
    """
    from app.core.db import SessionLocal
    from app.extraction.review import requeue_unresolved_titles

    with SessionLocal() as db:
        count = requeue_unresolved_titles(db)
    typer.echo(f"requeued {count} job(s); run 'xcelsior extract' to reprocess")


@review.command("reopen")
def review_reopen(item_ids: list[int]) -> None:
    """Return items to pending — undo a mistaken resolve or dismiss."""
    from app.core.db import SessionLocal
    from app.extraction.review import set_review_status

    with SessionLocal() as db:
        changed = set_review_status(db, item_ids, "pending")
    typer.echo(f"reopened {changed} item(s)")


if __name__ == "__main__":
    cli()
