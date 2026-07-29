import json
from datetime import UTC
from pathlib import Path

import pytest

from app.ingestion.connectors.lever import map_posting

FIXTURE = Path(__file__).parent / "fixtures" / "lever_posting.json"


@pytest.fixture
def payload() -> dict:
    return json.loads(FIXTURE.read_text())


def test_maps_recorded_payload(payload: dict) -> None:
    posting = map_posting(payload)

    assert posting is not None
    assert posting.external_id == payload["id"]
    assert posting.title == payload["text"]
    assert posting.apply_url == payload["hostedUrl"]
    assert posting.location_texts == payload["categories"]["allLocations"]
    assert posting.posted_at is not None
    assert posting.posted_at.tzinfo is UTC
    # createdAt is epoch milliseconds
    assert int(posting.posted_at.timestamp() * 1000) == payload["createdAt"]


def test_description_reassembles_all_body_parts(payload: dict) -> None:
    posting = map_posting(payload)

    assert posting is not None
    html = posting.description_html or ""
    assert payload["description"] in html
    for section in payload["lists"]:
        assert section["content"] in html
        assert f"<h3>{section['text']}</h3>" in html
    assert payload["additional"] in html
    # intro before sections before closing block
    assert html.index(payload["description"]) < html.index(payload["lists"][0]["content"])
    assert html.index(payload["lists"][-1]["content"]) < html.index(payload["additional"])


def test_non_us_posting_is_dropped(payload: dict) -> None:
    payload["country"] = "GB"

    assert map_posting(payload) is None


def test_missing_country_is_kept(payload: dict) -> None:
    del payload["country"]

    assert map_posting(payload) is not None


def test_content_hash_is_stable_and_change_sensitive(payload: dict) -> None:
    original = map_posting(payload).content_hash

    assert map_posting(payload).content_hash == original

    payload["text"] = payload["text"] + " (edited)"
    assert map_posting(payload).content_hash != original


def test_missing_optional_fields_do_not_crash() -> None:
    minimal = {"id": "abc-123", "text": "Engineer"}

    posting = map_posting(minimal)

    assert posting is not None
    assert posting.external_id == "abc-123"
    assert posting.description_html is None
    assert posting.location_texts == []
    assert posting.posted_at is None
    assert posting.employment_type is None


class TestEmploymentType:
    def test_commitment_from_recorded_payload(self, payload: dict) -> None:
        # The fixture declares "Full-time".
        assert map_posting(payload).employment_type == "full_time"

    @pytest.mark.parametrize(
        ("commitment", "expected"),
        [
            ("Intern", "internship"),
            ("Internship", "internship"),
            ("Co-op", "internship"),
            ("Student", "internship"),
            ("Part-time", "part_time"),
            ("Contract", "contract"),
            ("Temporary", "temporary"),
        ],
    )
    def test_commitment_vocabulary(self, payload: dict, commitment: str, expected: str) -> None:
        payload["categories"]["commitment"] = commitment

        assert map_posting(payload).employment_type == expected

    def test_missing_commitment_is_left_to_extraction(self, payload: dict) -> None:
        del payload["categories"]["commitment"]

        assert map_posting(payload).employment_type is None

    def test_unrecognized_commitment_is_left_to_extraction(self, payload: dict) -> None:
        payload["categories"]["commitment"] = "Band 4"

        assert map_posting(payload).employment_type is None
