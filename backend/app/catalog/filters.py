"""The canonical filter contract.

One model describes "which jobs are in scope" everywhere: the dashboard,
job search, skill pages, and saved searches all speak this shape. The
dashboard's click-through promise (a stat's number equals the search
result count behind it) holds only because both surfaces resolve the same
canonicalized filters through the same query builder.

Canonicalization also produces the analysis cache key: near-identical
queries ("radius 47 miles" vs "radius 50") converge onto one cache entry.
"""

import hashlib
import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

RADIUS_BUCKETS = (10, 25, 50, 100)
DEFAULT_RADIUS = 50

Arrangement = Literal["onsite", "hybrid", "remote"]
ExperienceLevel = Literal["entry", "mid", "senior", "staff_plus"]


class JobFilters(BaseModel):
    """Everything is optional; the empty filter means the national market."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    q: str | None = None  # free-text query (websearch syntax)
    title: str | None = None  # canonical title family slug
    location: str | None = None  # city slug, e.g. "san-francisco-ca"
    radius_miles: int = DEFAULT_RADIUS
    technologies: tuple[str, ...] = ()  # AND semantics across slugs
    arrangement: Arrangement | None = None
    experience_level: ExperienceLevel | None = None
    salary_min: int | None = None  # annual USD floor

    @field_validator("radius_miles")
    @classmethod
    def _bucket_radius(cls, v: int) -> int:
        """Snap to the nearest bucket at or above the requested radius.

        Buckets multiply cache hits at negligible fidelity cost; rounding
        *up* means a user never silently gets a smaller search area.
        """
        for bucket in RADIUS_BUCKETS:
            if v <= bucket:
                return bucket
        return RADIUS_BUCKETS[-1]

    @model_validator(mode="after")
    def _canonicalize(self) -> Self:
        if self.q is not None:
            # Whitespace and case never change what a tsquery matches;
            # collapsing them here converges cache keys.
            q = " ".join(self.q.lower().split())
            object.__setattr__(self, "q", q or None)
        deduped = tuple(sorted(set(t.lower() for t in self.technologies)))
        if deduped != self.technologies:
            object.__setattr__(self, "technologies", deduped)
        if self.title:
            object.__setattr__(self, "title", self.title.lower())
        if self.location:
            object.__setattr__(self, "location", self.location.lower())
        return self

    def canonical_dict(self) -> dict:
        """Stable, minimal form: defaults omitted so equivalent queries
        serialize identically regardless of how they were expressed."""
        out: dict = {}
        for field in sorted(self.__class__.model_fields):
            value = getattr(self, field)
            if field == "radius_miles":
                if self.location is not None:
                    out[field] = value  # radius is meaningless without a center
            elif value not in (None, ()):
                out[field] = list(value) if isinstance(value, tuple) else value
        return out

    def cache_key(self) -> str:
        payload = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def is_national(self) -> bool:
        return self.location is None
