from datetime import UTC, datetime

import httpx

from app.ingestion.connectors.base import NormalizedPosting, hash_payload

BOARD_URL = "https://api.lever.co/v0/postings/{token}"


def map_posting(posting: dict) -> NormalizedPosting | None:
    """Pure mapping from one Lever posting payload to the normalized shape.

    Kept free of I/O so it can be tested against recorded payloads.

    Returns None for postings Lever explicitly marks as non-US: this is a
    US-only product, and unlike Greenhouse, Lever states the country
    outright — dropping on that declared field is deterministic, not a
    location-string guess (those still go through the geo resolver).
    """
    country = posting.get("country")
    if country and country != "US":
        return None

    categories = posting.get("categories") or {}
    location_texts: list[str] = []
    for text in categories.get("allLocations") or []:
        if text and text not in location_texts:
            location_texts.append(text)
    single = categories.get("location")
    if single and single not in location_texts:
        location_texts.append(single)

    # Lever splits the body into an intro (`description`), titled sections
    # (`lists`), and a closing block (`additional`) — all already-real
    # HTML. Reassemble in display order so extraction sees the full text.
    parts: list[str] = []
    if posting.get("description"):
        parts.append(posting["description"])
    for section in posting.get("lists") or []:
        header = section.get("text")
        if header:
            parts.append(f"<h3>{header}</h3>")
        if section.get("content"):
            parts.append(section["content"])
    if posting.get("additional"):
        parts.append(posting["additional"])
    description_html = "\n".join(parts) or None

    posted_at: datetime | None = None
    if posting.get("createdAt"):
        posted_at = datetime.fromtimestamp(posting["createdAt"] / 1000, tz=UTC)

    return NormalizedPosting(
        external_id=str(posting["id"]),
        title=posting["text"],
        description_html=description_html,
        apply_url=posting.get("hostedUrl"),
        location_texts=location_texts,
        posted_at=posted_at,
        content_hash=hash_payload(posting),
        payload=posting,
    )


class LeverConnector:
    source_name = "lever"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": "XcelsiorBot/0.1 (job market analytics; contact in repo)"},
        )

    def fetch_postings(self, board_token: str) -> list[NormalizedPosting]:
        response = self._client.get(BOARD_URL.format(token=board_token), params={"mode": "json"})
        response.raise_for_status()
        mapped = (map_posting(posting) for posting in response.json())
        return [posting for posting in mapped if posting is not None]
