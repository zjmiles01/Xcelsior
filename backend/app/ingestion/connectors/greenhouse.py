import html
from datetime import datetime

import httpx

from app.ingestion.connectors.base import NormalizedPosting, hash_payload

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


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
