import json
from pathlib import Path

import pytest

from app.ingestion.connectors.greenhouse import map_posting

FIXTURE = Path(__file__).parent / "fixtures" / "greenhouse_job.json"


@pytest.fixture
def payload() -> dict:
    return json.loads(FIXTURE.read_text())


def test_maps_recorded_payload(payload: dict) -> None:
    posting = map_posting(payload)

    assert posting.external_id == str(payload["id"])
    assert posting.title == payload["title"]
    assert posting.apply_url == payload["absolute_url"]
    assert payload["location"]["name"] in posting.location_texts
    assert posting.posted_at is not None


def test_description_html_is_unescaped(payload: dict) -> None:
    posting = map_posting(payload)

    assert posting.description_html is not None
    assert "&lt;" not in posting.description_html
    assert "<p>" in posting.description_html


def test_content_hash_is_stable_and_change_sensitive(payload: dict) -> None:
    original = map_posting(payload).content_hash

    assert map_posting(payload).content_hash == original

    payload["title"] = payload["title"] + " (edited)"
    assert map_posting(payload).content_hash != original


def test_missing_optional_fields_do_not_crash() -> None:
    minimal = {"id": 1, "title": "Engineer"}

    posting = map_posting(minimal)

    assert posting.external_id == "1"
    assert posting.description_html is None
    assert posting.location_texts == []
    assert posting.posted_at is None
    assert posting.employment_type is None


class TestEmploymentType:
    def test_declared_in_board_metadata(self, payload: dict) -> None:
        payload["metadata"].append(
            {"id": 1, "name": "Employment Type", "value": "Intern", "value_type": "single_select"}
        )

        assert map_posting(payload).employment_type == "internship"

    def test_alternate_metadata_names(self, payload: dict) -> None:
        payload["metadata"] = [{"id": 1, "name": "Job Type", "value": "Part-time"}]

        assert map_posting(payload).employment_type == "part_time"

    def test_multi_select_metadata_value(self, payload: dict) -> None:
        payload["metadata"] = [{"id": 1, "name": "Worker Type", "value": ["Contract"]}]

        assert map_posting(payload).employment_type == "contract"

    def test_unrelated_metadata_is_ignored(self, payload: dict) -> None:
        # The recorded payload's metadata is all division/req-type noise.
        # Guessing from it would be worse than leaving the text classifier
        # to do the job downstream.
        assert map_posting(payload).employment_type is None

    def test_unrecognized_value_is_left_to_extraction(self, payload: dict) -> None:
        payload["metadata"] = [{"id": 1, "name": "Employment Type", "value": "Band 4"}]

        assert map_posting(payload).employment_type is None

    def test_null_and_malformed_metadata_do_not_crash(self, payload: dict) -> None:
        payload["metadata"] = [
            "not-a-dict",
            {"id": 1, "name": "Employment Type", "value": None},
            {"id": 2, "name": "Employment Type", "value": "Full-time"},
        ]

        assert map_posting(payload).employment_type == "full_time"
