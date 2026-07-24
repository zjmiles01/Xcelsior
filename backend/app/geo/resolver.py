"""US city resolution from free-text location strings.

Job postings write locations a hundred ways — "San Francisco, CA",
"San Francisco", "Seattle, WA, USA", "New York, New York, United States".
This module converges them onto one canonical city list (GeoNames-derived,
population >= 15k) so that geographic filters, radius queries, and metro
snapshots all agree on what "San Francisco" means.

Resolution is deliberately conservative: a string that doesn't clearly name
a known city resolves to None rather than to a guess. Unresolved strings
stay queryable via their raw text and are the input for growing the dataset.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "geo"
DATA_FILES = (DATA_DIR / "us_cities.csv", DATA_DIR / "us_cities_supplement.csv")
WORLD_CITIES_FILE = DATA_DIR / "world_city_names.txt"

# A bare name matching a famous non-US city may only resolve to a US city
# that is genuinely prominent — "London" must not mean London, OH just
# because Ohio's is the biggest London in the US.
MIN_POP_TO_BEAT_WORLD_CITY = 200_000
# A state name doubling as a city ("New York", "Washington") only falls
# back to city-lookup when the city is real-sized ("California" must not
# resolve to California, MD, population 12k).
MIN_POP_FOR_STATE_NAME_CITY = 100_000

# Country/region tokens that mark a posting as non-US outright. The
# resolver serves a US-only product; "London, UK" must resolve to nothing,
# not to the nearest same-named US town.
_NON_US_MARKERS = {
    "uk", "u.k.", "united kingdom", "england", "scotland", "wales", "ireland",
    "canada", "ontario", "british columbia", "quebec", "alberta",
    "france", "germany", "netherlands", "belgium", "spain", "portugal",
    "italy", "switzerland", "austria", "sweden", "norway", "denmark",
    "finland", "poland", "czechia", "czech republic", "romania", "greece",
    "hungary", "estonia", "latvia", "lithuania", "ukraine", "serbia",
    "croatia", "bulgaria", "slovakia", "slovenia", "türkiye", "turkey",
    "india", "china", "japan", "singapore", "south korea", "korea",
    "australia", "new zealand", "israel", "uae", "united arab emirates",
    "saudi arabia", "qatar", "egypt", "south africa", "nigeria", "kenya",
    "brazil", "mexico", "argentina", "chile", "colombia", "peru",
    "costa rica", "philippines", "indonesia", "malaysia", "thailand",
    "vietnam", "taiwan", "hong kong", "pakistan", "bangladesh",
}

_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}
_STATE_CODES = set(_STATE_NAMES.values())

# Tokens that name the country or add no geographic information.
_NOISE_SEGMENTS = {
    "us", "usa", "u.s.", "u.s.a.", "united states", "united states of america",
    "north america", "remote", "hybrid", "onsite", "on-site",
}

# Common posting spellings → GeoNames canonical names.
_CITY_ALIASES = {
    "new york": "new york city",
    "nyc": "new york city",
    "manhattan": "new york city",
    "saint louis": "st. louis",
    "st louis": "st. louis",
    "saint paul": "st. paul",
    "st paul": "st. paul",
    "washington dc": "washington",
    "washington d.c.": "washington",
    "washington, d.c.": "washington",
    "dc": "washington",
}

_SPLIT_RE = re.compile(r"[,;/|]|(?:\s[-–—]\s)")
_PREFIX_RE = re.compile(r"^(?:greater\s+|metro\s+|remote\s*[-–—:]?\s+)", re.IGNORECASE)
_SUFFIX_RE = re.compile(
    r"\s+(?:area|metro(?:politan)?\s+area|bay\s+area|hq|office)$", re.IGNORECASE
)


@dataclass(frozen=True)
class City:
    name: str
    state: str
    latitude: float
    longitude: float
    population: int

    @property
    def slug(self) -> str:
        city_part = re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")
        return f"{city_part}-{self.state.lower()}"

    @property
    def label(self) -> str:
        return f"{self.name}, {self.state}"


class GeoIndex:
    def __init__(self, cities: list[City], world_city_names: frozenset[str] = frozenset()) -> None:
        self._world_city_names = world_city_names
        self._by_city_state: dict[tuple[str, str], City] = {}
        self._by_city: dict[str, City] = {}
        self._by_slug: dict[str, City] = {}
        # Cities arrive population-descending, so the first occurrence of a
        # bare city name is the most populous one — the right ambiguity
        # default ("Portland" means Portland, OR, not Portland, ME).
        for city in cities:
            key = (city.name.lower(), city.state)
            self._by_city_state.setdefault(key, city)
            self._by_city.setdefault(city.name.lower(), city)
            self._by_slug.setdefault(city.slug, city)

    def lookup(self, city: str, state: str | None = None) -> City | None:
        name = city.lower().strip()
        name = _CITY_ALIASES.get(name, name)
        if state:
            return self._by_city_state.get((name, state.upper()))
        return self._by_city.get(name)

    def by_slug(self, slug: str) -> City | None:
        return self._by_slug.get(slug)

    def resolve(self, raw_text: str) -> City | None:
        """Resolve a free-text posting location to a canonical city."""
        segments = [s.strip() for s in _SPLIT_RE.split(raw_text) if s.strip()]
        explicit_state: str | None = None
        implied_state: str | None = None
        candidates: list[str] = []
        state_name_candidates: set[str] = set()
        for seg in segments:
            cleaned = _SUFFIX_RE.sub("", _PREFIX_RE.sub("", seg)).strip()
            low = cleaned.lower()
            if low in _NON_US_MARKERS:
                # "London, UK", "Toronto, Ontario, Canada": explicitly
                # non-US — never map to a same-named US town.
                return None
            if not cleaned or low in _NOISE_SEGMENTS:
                continue
            if len(cleaned) == 2 and cleaned.upper() in _STATE_CODES:
                # An explicit code always names the state ("Washington, DC"
                # must not let the city segment imply WA).
                explicit_state = explicit_state or cleaned.upper()
            elif low in _STATE_NAMES:
                # "New York, New York": a state name can also be the city,
                # so it is both a candidate and a (weaker) state signal.
                implied_state = implied_state or _STATE_NAMES[low]
                candidates.append(cleaned)
                state_name_candidates.add(cleaned)
            else:
                candidates.append(cleaned)

        state = explicit_state or implied_state
        for candidate in candidates:
            if state and (city := self.lookup(candidate, state)):
                return city
        for candidate in candidates:
            # Bare-name fallback: allowed when no state was given, or for a
            # state-name segment that implied its own state ("Washington"
            # alone means the city people mean, not a city in WA).
            if not state or candidate in state_name_candidates:
                city = self.lookup(candidate)
                if city is None:
                    continue
                if (
                    city.name.lower() in self._world_city_names
                    and city.population < MIN_POP_TO_BEAT_WORLD_CITY
                ):
                    # "Dublin" is Ireland unless the US Dublin is big
                    # enough to plausibly be meant without a state.
                    continue
                if (
                    candidate in state_name_candidates
                    and city.population < MIN_POP_FOR_STATE_NAME_CITY
                ):
                    continue
                return city
        return None


@lru_cache(maxsize=1)
def load_geo_index(data_files: tuple[Path, ...] = DATA_FILES) -> GeoIndex:
    cities: list[City] = []
    for data_file in data_files:
        with data_file.open(encoding="utf-8") as f:
            rows = csv.DictReader(line for line in f if not line.startswith("#"))
            for row in rows:
                cities.append(
                    City(
                        name=row["city"],
                        state=row["state"],
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                        population=int(row["population"]),
                    )
                )
    # Population-descending across all files so bare-name ambiguity always
    # resolves to the most populous holder of the name.
    cities.sort(key=lambda c: -c.population)
    world_names = frozenset(
        line.strip()
        for line in WORLD_CITIES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )
    return GeoIndex(cities, world_names)
