from trade_scout.common.stage_cache import BoundedStageCache, StageFingerprint


def _fingerprint(**dependencies: object) -> StageFingerprint:
    return StageFingerprint.build(
        stage="features",
        version="feature-materialization-v1",
        dependencies=dependencies,
    )


def test_fingerprint_is_stable_across_dependency_mapping_order() -> None:
    left = StageFingerprint.build(
        stage="features",
        version="v1",
        dependencies={"dataset": "daily-v1", "period": 20},
    )
    right = StageFingerprint.build(
        stage="features",
        version="v1",
        dependencies={"period": 20, "dataset": "daily-v1"},
    )

    assert left == right


def test_downstream_only_change_does_not_invalidate_upstream_fingerprint() -> None:
    upstream = _fingerprint(dataset="daily-v1", feature="sma", period=20)
    same_upstream = _fingerprint(dataset="daily-v1", feature="sma", period=20)

    stop_10 = StageFingerprint.build(
        stage="exits",
        version="fixed-stop-v1",
        dependencies={"upstream": upstream.digest, "stop_pct": 0.10},
    )
    stop_12 = StageFingerprint.build(
        stage="exits",
        version="fixed-stop-v1",
        dependencies={"upstream": upstream.digest, "stop_pct": 0.12},
    )

    assert upstream == same_upstream
    assert stop_10 != stop_12


def test_cache_reuses_exact_stage_result() -> None:
    cache: BoundedStageCache[tuple[int, ...]] = BoundedStageCache(max_entries=2)
    key = _fingerprint(dataset="daily-v1", feature="return_20")
    calls = 0

    def compute() -> tuple[int, ...]:
        nonlocal calls
        calls += 1
        return (1, 2, 3)

    assert cache.get_or_compute(key, compute) == (1, 2, 3)
    assert cache.get_or_compute(key, compute) == (1, 2, 3)
    assert calls == 1
    assert cache.stats().hits == 1
    assert cache.stats().misses == 1


def test_cache_evicts_least_recently_used_stage() -> None:
    cache: BoundedStageCache[str] = BoundedStageCache(max_entries=2)
    first = _fingerprint(dataset="v1", period=10)
    second = _fingerprint(dataset="v1", period=20)
    third = _fingerprint(dataset="v1", period=30)

    cache.put(first, "first")
    cache.put(second, "second")
    assert cache.get(first) == "first"
    cache.put(third, "third")

    assert cache.get(second) is None
    assert cache.get(first) == "first"
    assert cache.get(third) == "third"
    assert cache.stats().evictions == 1


def test_stage_or_version_change_invalidates_cache_identity() -> None:
    dependencies = {"dataset": "daily-v1", "feature": "atr", "period": 14}

    feature_v1 = StageFingerprint.build(
        stage="features", version="v1", dependencies=dependencies
    )
    feature_v2 = StageFingerprint.build(
        stage="features", version="v2", dependencies=dependencies
    )
    event_v1 = StageFingerprint.build(
        stage="events", version="v1", dependencies=dependencies
    )

    assert feature_v1 != feature_v2
    assert feature_v1 != event_v1
