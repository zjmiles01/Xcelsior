import html
from datetime import datetime

import httpx

from app.catalog.employment import normalize_declared
from app.ingestion.connectors.base import NormalizedPosting, hash_payload

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"

# Greenhouse has no standard employment-type field; boards that publish one
# put it in the free-form `metadata` list under a name of their choosing.
# These are the names seen in practice — anything else is left to the text
# classifier rather than guessed at.
_EMPLOYMENT_METADATA_NAMES = frozenset(
    {
        "employment type",
        "employment status",
        "job type",
        "job type / employment type",
        "position type",
        "role type",
        "worker type",
        "work type",
        "contract type",
        "employee type",
        "type of employment",
    }
)


def _employment_type(job: dict) -> str | None:
    """Employment type as declared by the board's metadata, if any."""
    for entry in job.get("metadata") or []:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip().lower()
        if name not in _EMPLOYMENT_METADATA_NAMES:
            continue
        value = entry.get("value")
        # Multi-select metadata arrives as a list; single-select as a string.
        if isinstance(value, list):
            for item in value:
                declared = normalize_declared(item if isinstance(item, str) else None)
                if declared is not None:
                    return declared
            continue
        declared = normalize_declared(value if isinstance(value, str) else None)
        if declared is not None:
            return declared
    return None


def map_posting(job: dict) -> NormalizedPosting:
    """Pure mapping from one Greenhouse job payload to the normalized shape.

    Kept free of I/O so it can be tested against recorded payloads.
    """
    location_texts: list[str] = []
    location = (job.get("location") or {}).get("name")
    if location:
        location_texts.append(location)
    for office in job.get("offices") or []:
        name = office.get("name")
        if name and name not in location_texts:
            location_texts.append(name)

    posted_at: datetime | None = None
    if job.get("updated_at"):
        posted_at = datetime.fromisoformat(job["updated_at"])

    # Greenhouse serves description HTML entity-escaped inside a JSON string.
    content = job.get("content")
    description_html = html.unescape(content) if content else None

    return NormalizedPosting(
        external_id=str(job["id"]),
        title=job["title"],
        description_html=description_html,
        apply_url=job.get("absolute_url"),
        location_texts=location_texts,
        posted_at=posted_at,
        content_hash=hash_payload(job),
        employment_type=_employment_type(job),
        payload=job,
    )


class GreenhouseConnector:
    source_name = "greenhouse"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": "XcelsiorBot/0.1 (job market analytics; contact in repo)"},
        )

    def fetch_postings(self, board_token: str) -> list:
        response = self._client.get(
            BOARD_URL.format(token=board_token), params={"content": "true"}
        )
        response.raise_for_status()
        return [map_posting(job) for job in response.json().get("jobs", [])]
