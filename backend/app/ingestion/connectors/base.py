import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


def hash_payload(payload: dict) -> str:
    """Canonical content hash for change detection, shared by connectors."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class NormalizedPosting:
    """Source-independent shape every connector maps into. The pipeline core
    only ever sees this type; source-specific payload quirks stop here."""

    external_id: str
    title: str
    description_html: str | None
    apply_url: str | None
    location_texts: list[str]
    posted_at: datetime | None
    content_hash: str
    # What the source itself declared, mapped onto our vocabulary
    # (app/catalog/employment.py). None when the board says nothing we
    # recognize — extraction then infers it from the text.
    employment_type: str | None = None
    payload: dict = field(repr=False, default_factory=dict)


class CompanyBoardConnector(Protocol):
    """Port for ATS sources that expose one public board per company.

    Aggregator APIs (Adzuna, USAJobs) don't fit this shape; that second
    connector family gets its own protocol when its first implementation
    lands, rather than being guessed at now.
    """

    source_name: str

    def fetch_postings(self, board_token: str) -> list[NormalizedPosting]: ...


@dataclass(frozen=True)
class ConnectorSpec:
    """A source declared to the pipeline: how to build its connector, and
    the metadata its `sources` row is created with.

    The spec is authoritative only at creation time; afterwards the
    database row is the runtime authority (notably `enabled`, which is an
    operational switch, not code).
    """

    factory: Callable[[], CompanyBoardConnector]
    kind: str  # ats_api | aggregator_api | gov_api
    display_policy: str = "full_text"  # full_text | extracted_only
    attribution_text: str | None = None
    attribution_url: str | None = None
