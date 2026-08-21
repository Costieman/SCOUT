from pathlib import Path

from trade_scout.common.stage_checkpoint import FileStageCheckpointStore


def test_completed_asset_is_skipped_on_restart(tmp_path: Path) -> None:
    store = FileStageCheckpointStore(tmp_path)
    store.mark_completed(
        operation_id="sp500-import",
        stage="identity",
        asset="AAPL",
        fingerprint="identity-v1:aapl",
    )

    remaining = store.incomplete_assets(
        operation_id="sp500-import",
        stage="identity",
        assets=("AAPL", "MSFT"),
        fingerprint_by_asset={
            "AAPL": "identity-v1:aapl",
            "MSFT": "identity-v1:msft",
        },
    )

    assert remaining == ("MSFT",)


def test_changed_fingerprint_invalidates_only_that_asset(tmp_path: Path) -> None:
    store = FileStageCheckpointStore(tmp_path)
    for asset in ("AAPL", "MSFT"):
        store.mark_completed(
            operation_id="sp500-import",
            stage="reconciliation",
            asset=asset,
            fingerprint=f"reconcile-v1:{asset.lower()}",
        )

    remaining = store.incomplete_assets(
        operation_id="sp500-import",
        stage="reconciliation",
        assets=("AAPL", "MSFT"),
        fingerprint_by_asset={
            "AAPL": "reconcile-v2:aapl",
            "MSFT": "reconcile-v1:msft",
        },
    )

    assert remaining == ("AAPL",)


def test_stage_boundaries_are_independent(tmp_path: Path) -> None:
    store = FileStageCheckpointStore(tmp_path)
    store.mark_completed(
        operation_id="sp500-import",
        stage="identity",
        asset="AAPL",
        fingerprint="identity-v1:aapl",
    )

    assert store.completed(
        operation_id="sp500-import",
        stage="identity",
        asset="AAPL",
        fingerprint="identity-v1:aapl",
    )
    assert not store.completed(
        operation_id="sp500-import",
        stage="promotion",
        asset="AAPL",
        fingerprint="promotion-v1:aapl",
    )


def test_checkpoint_is_durable_across_store_instances(tmp_path: Path) -> None:
    first = FileStageCheckpointStore(tmp_path)
    first.mark_completed(
        operation_id="sp500-import",
        stage="promotion",
        asset="AAPL",
        fingerprint="promotion-v1:aapl",
    )

    restarted = FileStageCheckpointStore(tmp_path)
    assert restarted.completed(
        operation_id="sp500-import",
        stage="promotion",
        asset="AAPL",
        fingerprint="promotion-v1:aapl",
    )
