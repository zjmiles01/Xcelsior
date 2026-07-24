from app.catalog.filters import JobFilters


def test_equivalent_filters_share_a_cache_key():
    a = JobFilters(technologies=("python", "go"), title="Backend-Engineer")
    b = JobFilters(technologies=("GO", "python", "go"), title="backend-engineer")
    assert a.cache_key() == b.cache_key()
    assert a.technologies == ("go", "python")


def test_different_filters_differ():
    a = JobFilters(technologies=("python",))
    b = JobFilters(technologies=("python",), arrangement="remote")
    assert a.cache_key() != b.cache_key()


def test_radius_buckets_round_up():
    assert JobFilters(radius_miles=1).radius_miles == 10
    assert JobFilters(radius_miles=10).radius_miles == 10
    assert JobFilters(radius_miles=11).radius_miles == 25
    assert JobFilters(radius_miles=47).radius_miles == 50
    assert JobFilters(radius_miles=51).radius_miles == 100
    assert JobFilters(radius_miles=400).radius_miles == 100


def test_radius_irrelevant_without_location():
    # "Any radius, no center" must not fragment the cache.
    assert JobFilters(radius_miles=10).cache_key() == JobFilters(radius_miles=100).cache_key()
    assert (
        JobFilters(location="denver-co", radius_miles=10).cache_key()
        != JobFilters(location="denver-co", radius_miles=100).cache_key()
    )


def test_q_canonicalizes_whitespace_and_case():
    a = JobFilters(q="  Senior   Platform  ")
    b = JobFilters(q="senior platform")
    assert a.q == "senior platform"
    assert a.cache_key() == b.cache_key()
    assert JobFilters(q="   ").q is None


def test_empty_filter_is_national():
    f = JobFilters()
    assert f.is_national()
    assert f.canonical_dict() == {}
