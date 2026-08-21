from threading import Lock
from time import sleep

from trade_scout.common.bounded_asset_executor import execute_assets_bounded


def test_results_preserve_input_order() -> None:
    results = execute_assets_bounded((3, 1, 2), lambda value: value * 10, max_workers=2)
    assert tuple(item.asset for item in results) == (3, 1, 2)
    assert tuple(item.value for item in results) == (30, 10, 20)


def test_failure_is_localized_without_cancelling_other_assets() -> None:
    def worker(asset: str) -> str:
        if asset == "BAD":
            raise ValueError("invalid identity")
        return asset.lower()

    results = execute_assets_bounded(("AAPL", "BAD", "MSFT"), worker, max_workers=3)

    assert results[0].succeeded and results[0].value == "aapl"
    assert not results[1].succeeded
    assert results[1].asset == "BAD"
    assert results[1].error_type == "ValueError"
    assert results[2].succeeded and results[2].value == "msft"


def test_concurrency_never_exceeds_bound() -> None:
    lock = Lock()
    active = 0
    observed_max = 0

    def worker(asset: int) -> int:
        nonlocal active, observed_max
        with lock:
            active += 1
            observed_max = max(observed_max, active)
        sleep(0.01)
        with lock:
            active -= 1
        return asset

    execute_assets_bounded(range(12), worker, max_workers=3)
    assert observed_max <= 3
