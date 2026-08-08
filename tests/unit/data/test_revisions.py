from datetime import date

import pytest

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.data.revisions import RevisionConflictError, build_canonical_revision

V1 = DatasetVersion("equities_daily_v1.0.0")
V2 = DatasetVersion("equities_daily_v1.0.1")


def _bar(
    instrument_id: str,
    trade_date: date,
    *,
    close: float = 100.0,
    volume: int = 1_000_000,
    dataset_version: DatasetVersion = V1,
    provider_id: str = "primary",
) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=trade_date,
        open_raw=close,
        high_raw=close + 1.0,
        low_raw=close - 1.0,
        close_raw=close,
        volume_raw=volume,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close,
        high_split_adjusted=close + 1.0,
        low_split_adjusted=close - 1.0,
        close_split_adjusted=close,
        provider_id=provider_id,
        dataset_version=dataset_version,
        quality_status=QualityStatus.PASS,
    )


def test_incremental_revision_appends_new_session_without_mutating_parent() -> None:
    base = (
        _bar("tsi-1", date(2026, 8, 6)),
        _bar("tsi-1", date(2026, 8, 7)),
    )
    incoming = (_bar("tsi-1", date(2026, 8, 8), close=101.0, dataset_version=V2),)

    result = build_canonical_revision(
        base,
        incoming,
        target_dataset_version=V2,
        correction_window_start=date(2026, 8, 6),
    )

    assert result.parent_dataset_version == V1
    assert result.target_dataset_version == V2
    assert result.requires_new_version is True
    assert [(item.instrument_id, item.trade_date) for item in result.added] == [
        (InstrumentId("tsi-1"), date(2026, 8, 8))
    ]
    assert result.revised == ()
    assert result.carried_forward_count == 2
    assert all(bar.dataset_version == V2 for bar in result.bars)
    assert all(bar.dataset_version == V1 for bar in base)


def test_correction_inside_lookback_replaces_exact_key() -> None:
    base = (
        _bar("tsi-1", date(2026, 8, 6), close=100.0),
        _bar("tsi-1", date(2026, 8, 7), close=101.0),
    )
    incoming = (_bar("tsi-1", date(2026, 8, 7), close=101.5, dataset_version=V2),)

    result = build_canonical_revision(
        base,
        incoming,
        target_dataset_version=V2,
        correction_window_start=date(2026, 8, 6),
    )

    assert result.added == ()
    assert [(item.instrument_id, item.trade_date) for item in result.revised] == [
        (InstrumentId("tsi-1"), date(2026, 8, 7))
    ]
    assert result.carried_forward_count == 1
    corrected = next(bar for bar in result.bars if bar.trade_date == date(2026, 8, 7))
    assert corrected.close_raw == 101.5


def test_identical_lookback_observation_does_not_require_new_version() -> None:
    base = (_bar("tsi-1", date(2026, 8, 7), close=101.0),)
    incoming = (_bar("tsi-1", date(2026, 8, 7), close=101.0, dataset_version=V2),)

    result = build_canonical_revision(
        base,
        incoming,
        target_dataset_version=V2,
        correction_window_start=date(2026, 8, 6),
    )

    assert result.requires_new_version is False
    assert len(result.unchanged_incoming) == 1
    assert result.carried_forward_count == 1


def test_correction_before_explicit_lookback_window_fails() -> None:
    base = (_bar("tsi-1", date(2026, 8, 1), close=100.0),)
    incoming = (_bar("tsi-1", date(2026, 8, 1), close=99.0, dataset_version=V2),)

    with pytest.raises(RevisionConflictError, match="precedes correction window"):
        build_canonical_revision(
            base,
            incoming,
            target_dataset_version=V2,
            correction_window_start=date(2026, 8, 5),
        )


def test_incremental_input_never_deletes_absent_parent_history() -> None:
    base = (
        _bar("tsi-1", date(2026, 8, 6)),
        _bar("tsi-2", date(2026, 8, 6)),
    )
    incoming = (_bar("tsi-1", date(2026, 8, 7), dataset_version=V2),)

    result = build_canonical_revision(
        base,
        incoming,
        target_dataset_version=V2,
        correction_window_start=date(2026, 8, 6),
    )

    keys = {(bar.instrument_id, bar.trade_date) for bar in result.bars}
    assert (InstrumentId("tsi-2"), date(2026, 8, 6)) in keys


def test_incoming_provider_and_target_version_must_match_parent_policy() -> None:
    base = (_bar("tsi-1", date(2026, 8, 6)),)

    with pytest.raises(RevisionConflictError, match="differs from canonical provider"):
        build_canonical_revision(
            (_bar("tsi-1", date(2026, 8, 6)),),
            (
                _bar(
                    "tsi-1",
                    date(2026, 8, 7),
                    dataset_version=V2,
                    provider_id="other",
                ),
            ),
            target_dataset_version=V2,
            correction_window_start=date(2026, 8, 6),
        )

    with pytest.raises(RevisionConflictError, match="expected target version"):
        build_canonical_revision(
            base,
            (_bar("tsi-1", date(2026, 8, 7), dataset_version=V1),),
            target_dataset_version=V2,
            correction_window_start=date(2026, 8, 6),
        )


def test_duplicate_incoming_keys_fail_instead_of_last_write_wins() -> None:
    base = (_bar("tsi-1", date(2026, 8, 6)),)
    duplicate = _bar("tsi-1", date(2026, 8, 7), dataset_version=V2)

    with pytest.raises(RevisionConflictError, match="duplicate instrument/session"):
        build_canonical_revision(
            base,
            (duplicate, duplicate),
            target_dataset_version=V2,
            correction_window_start=date(2026, 8, 6),
        )


def test_result_order_is_deterministic() -> None:
    base = (
        _bar("tsi-2", date(2026, 8, 6)),
        _bar("tsi-1", date(2026, 8, 7)),
        _bar("tsi-1", date(2026, 8, 6)),
    )

    result = build_canonical_revision(
        reversed(base),
        (),
        target_dataset_version=V2,
        correction_window_start=date(2026, 8, 6),
    )

    assert [(str(bar.instrument_id), bar.trade_date) for bar in result.bars] == [
        ("tsi-1", date(2026, 8, 6)),
        ("tsi-1", date(2026, 8, 7)),
        ("tsi-2", date(2026, 8, 6)),
    ]
