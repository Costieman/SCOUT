# Canonical daily-bar normalization

Provider adapters terminate vendor-specific field names and transport behavior. The canonical normalization step then converts `ProviderDailyBar` records into `DailyBar` only when identity and adjustment semantics are explicit.

## Rules

- Provider identity is resolved only through the permanent instrument master. Ticker matching is never used as a fallback.
- Continuity-series providers must use `normalize_provider_daily_bars_identity_aware`. Every resolved bar must also have exactly one dated canonical `SymbolHistoryRecord` covering its trade date. Missing coverage is quarantined as `UNRESOLVED_SYMBOL_HISTORY`; contradictory overlapping history remains a hard symbol-history conflict.
- The provider bar's `symbol` is retrieval/provenance metadata, not the historical canonical symbol. It is deliberately **not** required to equal the symbol effective on the bar date. A provider may serve predecessor history through a current query ticker; canonical continuity is carried by permanent `instrument_id`, while historical display symbols are resolved separately by date.
- `split_factor` must be supplied explicitly by the adapter. A missing value is quarantined rather than interpreted as `1.0`.
- `dividend_cash` must be supplied explicitly by the adapter. A missing value is quarantined rather than interpreted as zero.
- Split-adjusted OHLC may be entirely unavailable, but a partially populated adjusted bar is quarantined.
- Raw provider OHLCV values are copied without repair or coercive reinterpretation.
- Canonical structural/market-logic checks run after normalization. Their record-level worst quality state is attached to the resulting `DailyBar`.
- Duplicate canonical instrument/session observations are rejected by the quality layer.

Records that cannot be normalized are retained as machine-readable `NormalizationIssue` entries. They are not guessed, repaired, or silently dropped from the audit result. Subsequent completeness checks can therefore distinguish missing canonical coverage from apparently complete data.

The legacy `normalize_provider_daily_bars` entry point remains available for providers/workflows whose dated symbol-history gate is established elsewhere. It must not be used to promote a provider continuity series whose historical ticker lineage has not been resolved.

This layer does not decide whether a provider's adjustment semantics are acceptable. That evidence belongs to provider evaluation and the provider adapter's capability/limitation declaration.
