from collections.abc import Sequence
from datetime import date

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.provider import (
    CorporateActionRequest,
    DailyBarRequest,
    DataFamily,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderCorporateAction,
    ProviderDailyBar,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderInstrument,
    ProviderSymbolHistory,
)


class FakeProvider:
    provider_id = "fake"

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            data_families=frozenset({DataFamily.DAILY_BARS}),
            adjustment_modes=frozenset({PriceRepresentation.RAW}),
            earliest_daily_bar_date=date(2000, 1, 1),
            supports_delisted=False,
            supports_symbol_history=False,
            timestamp_convention="exchange session date",
            known_limitations=(),
        )

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(self.provider_id, ProviderHealthStatus.HEALTHY)

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]:
        return ()

    def get_symbol_history(
        self, *, provider_instrument_ids: Sequence[str] | None = None
    ) -> Sequence[ProviderSymbolHistory]:
        return ()

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]:
        return ()

    def get_corporate_actions(
        self, request: CorporateActionRequest
    ) -> Sequence[ProviderCorporateAction]:
        return ()


def test_structural_provider_protocol_accepts_vendor_adapter() -> None:
    assert isinstance(FakeProvider(), ProviderAdapter)


def test_daily_bar_request_rejects_reverse_date_range() -> None:
    try:
        DailyBarRequest(start=date(2026, 8, 8), end=date(2026, 8, 7))
    except ValueError as exc:
        assert "end date" in str(exc)
    else:
        raise AssertionError("expected invalid request to fail")
