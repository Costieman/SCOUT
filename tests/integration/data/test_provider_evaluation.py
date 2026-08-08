from collections.abc import Sequence
from datetime import date

from trade_scout.data.contracts import (
    CorporateActionType,
    DatasetVersion,
    PriceRepresentation,
    SecurityType,
)
from trade_scout.data.provider import (
    CorporateActionRequest,
    DailyBarRequest,
    DataFamily,
    ProviderCapabilities,
    ProviderCorporateAction,
    ProviderDailyBar,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderInstrument,
    ProviderSymbolHistory,
)
from trade_scout.data.provider_evaluation import (
    EvaluationState,
    ProviderEvaluationCase,
    evaluate_provider_adapter,
)


class FakeEvaluationProvider:
    provider_id = "candidate"

    def __init__(self, *, supports_delisted: bool = True) -> None:
        self.supports_delisted = supports_delisted

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            data_families=frozenset(
                {
                    DataFamily.INSTRUMENTS,
                    DataFamily.SYMBOL_HISTORY,
                    DataFamily.DAILY_BARS,
                    DataFamily.CORPORATE_ACTIONS,
                    DataFamily.STATUS_DELISTINGS,
                }
            ),
            adjustment_modes=frozenset(
                {PriceRepresentation.RAW, PriceRepresentation.SPLIT_ADJUSTED}
            ),
            earliest_daily_bar_date=date(2000, 1, 1),
            supports_delisted=self.supports_delisted,
            supports_symbol_history=True,
            timestamp_convention="exchange session date",
            known_limitations=(),
        )

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderHealthStatus.HEALTHY,
        )

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]:
        return (
            ProviderInstrument(
                provider_id=self.provider_id,
                provider_instrument_id="asset-1",
                symbol="AAA",
                name="Example Corp",
                exchange="XNYS",
                security_type=SecurityType.COMMON_STOCK,
                currency="USD",
                active=False,
                first_trade_date=date(2010, 1, 4),
                end_date=date(2020, 6, 30),
                source_fields={"figi": "BBG-EXAMPLE"},
            ),
        )

    def get_symbol_history(
        self, *, provider_instrument_ids: Sequence[str] | None = None
    ) -> Sequence[ProviderSymbolHistory]:
        return (
            ProviderSymbolHistory(
                provider_id=self.provider_id,
                provider_instrument_id="asset-1",
                symbol="AAA",
                exchange="XNYS",
                effective_from=date(2010, 1, 4),
                effective_to=date(2020, 6, 30),
            ),
        )

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]:
        return (
            ProviderDailyBar(
                provider_id=self.provider_id,
                provider_instrument_id="asset-1",
                symbol="AAA",
                trade_date=date(2020, 6, 29),
                open=100.0,
                high=105.0,
                low=99.0,
                close=103.0,
                volume=1_000_000,
                split_factor=1.0,
                dividend_cash=0.0,
                adjusted_open=100.0,
                adjusted_high=105.0,
                adjusted_low=99.0,
                adjusted_close=103.0,
            ),
        )

    def get_corporate_actions(
        self, request: CorporateActionRequest
    ) -> Sequence[ProviderCorporateAction]:
        return (
            ProviderCorporateAction(
                provider_id=self.provider_id,
                provider_instrument_id="asset-1",
                source_event_id="split-1",
                action_type=CorporateActionType.SPLIT,
                effective_date=date(2020, 6, 30),
                source_fields={"ratio": "2:1"},
            ),
        )


def _case(**overrides: object) -> ProviderEvaluationCase:
    values: dict[str, object] = {
        "case_id": "delisted-split-case",
        "provider_instrument_id": "asset-1",
        "provider_symbol": "AAA",
        "start": date(2020, 6, 1),
        "end": date(2020, 6, 30),
        "expected_active": False,
        "required_action_types": frozenset({CorporateActionType.SPLIT}),
        "require_symbol_history": True,
    }
    values.update(overrides)
    return ProviderEvaluationCase(**values)  # type: ignore[arg-type]


def test_reusable_harness_passes_automated_case_but_does_not_accept_provider() -> None:
    report = evaluate_provider_adapter(
        FakeEvaluationProvider(),
        (_case(),),
        dataset_version=DatasetVersion("evaluation-v0.1.0"),
    )

    assert report.automated_gate_passed is True
    assert report.provider_accepted is False
    assert report.unresolved_manual_gates
    assert report.cases[0].daily_bar_count == 1
    assert report.cases[0].corporate_action_count == 1


def test_delisted_support_is_a_hard_automated_failure() -> None:
    report = evaluate_provider_adapter(
        FakeEvaluationProvider(supports_delisted=False),
        (_case(),),
        dataset_version=DatasetVersion("evaluation-v0.1.0"),
    )

    check = next(item for item in report.checks if item.check_id == "delisted_instrument_support")
    assert check.state is EvaluationState.FAIL
    assert report.automated_gate_passed is False


def test_case_fails_when_exact_provider_identity_cannot_be_discovered() -> None:
    report = evaluate_provider_adapter(
        FakeEvaluationProvider(),
        (_case(provider_instrument_id="unknown-asset"),),
        dataset_version=DatasetVersion("evaluation-v0.1.0"),
    )

    case = report.cases[0]
    assert case.automated_gate_passed is False
    assert case.checks[0].check_id == "instrument_identity"
    assert case.checks[0].state is EvaluationState.FAIL


def test_case_fails_when_required_corporate_action_is_absent() -> None:
    report = evaluate_provider_adapter(
        FakeEvaluationProvider(),
        (_case(required_action_types=frozenset({CorporateActionType.MERGER})),),
        dataset_version=DatasetVersion("evaluation-v0.1.0"),
    )

    check = next(
        item for item in report.cases[0].checks if item.check_id == "required_corporate_actions"
    )
    assert check.state is EvaluationState.FAIL


def test_case_validates_requested_active_status() -> None:
    report = evaluate_provider_adapter(
        FakeEvaluationProvider(),
        (_case(expected_active=True),),
        dataset_version=DatasetVersion("evaluation-v0.1.0"),
    )

    check = next(item for item in report.cases[0].checks if item.check_id == "active_status")
    assert check.state is EvaluationState.FAIL
