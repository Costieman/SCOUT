from __future__ import annotations

from datetime import date

from trade_scout.data.contracts import CorporateActionType
from trade_scout.data.corporate_action_evidence import (
    CorporateActionEvidenceState,
    evaluate_corporate_action_evidence,
)
from trade_scout.data.provider import ProviderCorporateAction, ProviderDailyBar


def _bar(day: int, close: float) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id="fixture",
        provider_instrument_id="fixture:ABC",
        symbol="ABC",
        trade_date=date(2020, 1, day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
    )


def _action(day: int, action_type: CorporateActionType) -> ProviderCorporateAction:
    return ProviderCorporateAction(
        provider_id="fixture",
        provider_instrument_id="fixture:ABC",
        source_event_id=f"event-{day}-{action_type.value}",
        action_type=action_type,
        effective_date=date(2020, 1, day),
        source_fields={},
    )


def test_large_price_move_is_flagged_with_nearby_split_without_causal_claim() -> None:
    report = evaluate_corporate_action_evidence(
        provider_id="fixture",
        actions=(_action(3, CorporateActionType.SPLIT),),
        bars=(_bar(2, 100.0), _bar(3, 50.0), _bar(4, 51.0)),
        start=date(2020, 1, 1),
        end=date(2020, 1, 5),
        expected_action_types=frozenset({CorporateActionType.SPLIT}),
        discontinuity_threshold=0.35,
    )

    assert report.passed is True
    assert len(report.discontinuities) == 1
    assert report.discontinuities[0].nearby_action_types == (CorporateActionType.SPLIT,)
    assert report.discontinuities[0].has_nearby_action is True


def test_large_unexplained_move_remains_visible() -> None:
    report = evaluate_corporate_action_evidence(
        provider_id="fixture",
        actions=(),
        bars=(_bar(2, 100.0), _bar(3, 50.0)),
        start=date(2020, 1, 1),
        end=date(2020, 1, 5),
        discontinuity_threshold=0.35,
    )

    assert len(report.discontinuities) == 1
    assert report.discontinuities[0].has_nearby_action is False


def test_missing_configured_action_type_fails_evidence_check() -> None:
    report = evaluate_corporate_action_evidence(
        provider_id="fixture",
        actions=(_action(3, CorporateActionType.SPLIT),),
        bars=(_bar(2, 100.0), _bar(3, 50.0)),
        start=date(2020, 1, 1),
        end=date(2020, 1, 5),
        expected_action_types=frozenset(
            {CorporateActionType.SPLIT, CorporateActionType.CASH_DIVIDEND}
        ),
    )

    check = next(item for item in report.checks if item.check_id == "expected_action_types")
    assert check.state is CorporateActionEvidenceState.FAIL
    assert "cash_dividend" in check.detail
    assert report.passed is False
