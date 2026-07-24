import pytest

from app.geo.resolver import load_geo_index


@pytest.fixture(scope="module")
def index():
    return load_geo_index()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("San Francisco, CA", ("San Francisco", "CA")),
        ("San Francisco", ("San Francisco", "CA")),
        ("Seattle, WA, USA", ("Seattle", "WA")),
        ("New York, NY", ("New York City", "NY")),
        ("New York, New York, United States", ("New York City", "NY")),
        ("Austin, Texas", ("Austin", "TX")),
        ("Remote - San Francisco", ("San Francisco", "CA")),
        ("Greater Boston Area", ("Boston", "MA")),
        ("Chicago, IL; New York, NY", ("Chicago", "IL")),
        ("Cambridge, MA", ("Cambridge", "MA")),
    ],
)
def test_resolves(index, raw, expected):
    city = index.resolve(raw)
    assert city is not None, f"{raw!r} did not resolve"
    assert (city.name, city.state) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Remote",
        "Remote - US",
        "United States",
        "US-PERM",
        "EMEA",
        "Anywhere",
    ],
)
def test_non_cities_stay_unresolved(index, raw):
    assert index.resolve(raw) is None


def test_bare_ambiguous_name_prefers_population(index):
    # Portland, OR (pop ~650k) over Portland, ME (~68k).
    city = index.resolve("Portland")
    assert (city.name, city.state) == ("Portland", "OR")


def test_state_disambiguates(index):
    city = index.resolve("Portland, ME")
    assert (city.name, city.state) == ("Portland", "ME")


def test_wrong_state_does_not_fall_back(index):
    # Conservative: a city+state pair that doesn't exist must not silently
    # resolve to the same-named city elsewhere.
    assert index.resolve("Cupertino, TX") is None


def test_slug_round_trip(index):
    city = index.resolve("San Francisco, CA")
    assert city.slug == "san-francisco-ca"
    assert index.by_slug("san-francisco-ca") == city


def test_new_york_alias(index):
    # GeoNames' canonical name is "New York City"; the bare "New York"
    # string must still resolve (it is also the state name).
    city = index.resolve("New York")
    assert (city.name, city.state) == ("New York City", "NY")


def test_dc_explicit_code_beats_state_name_inference(index):
    city = index.resolve("Washington, DC")
    assert (city.name, city.state) == ("Washington", "DC")


def test_bare_washington_means_the_city(index):
    city = index.resolve("Washington")
    assert (city.name, city.state) == ("Washington", "DC")


def test_supplement_file_cities_resolve(index):
    city = index.resolve("Starbase, TX")
    assert (city.name, city.state) == ("Starbase", "TX")


@pytest.mark.parametrize(
    "raw",
    [
        "London, UK",
        "London",
        "Dublin, Ireland",
        "Dublin",
        "Paris, France",
        "Paris",
        "Toronto, Ontario",
        "Vancouver",
        "Amsterdam",
        "Mexico City, Mexico",
        "Bengaluru, India",
        "Singapore",
        "California",
    ],
)
def test_international_locations_never_map_to_us_towns(index, raw):
    # A US-only index must refuse famous world cities and bare region
    # names rather than resolving them to small same-named US towns
    # (London -> London, OH was a real corpus bug).
    assert index.resolve(raw) is None


def test_explicit_state_still_reaches_small_towns(index):
    # The world-city guard applies only to bare names; residents of the
    # actual Dublin, CA can still say so explicitly.
    city = index.resolve("Dublin, CA")
    assert (city.name, city.state) == ("Dublin", "CA")
    city = index.resolve("Paris, TX")
    assert (city.name, city.state) == ("Paris", "TX")
