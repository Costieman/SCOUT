# Canonical daily-bar normalization

Provider adapters terminate vendor-specific field names and transport behavior. The canonical normalization step then converts `ProviderDailyBar` records into `DailyBar` only when identity and adjustment semantics are explicit.

## Rules

- Provider identity is resolved only through the permanent instrument master. Ticker matching is never used as a fallback.
- `split_factor` must be supplied explicitly by the adapter. A missing value is quarantined rather than interpreted as `1.0`.
- `dividend_cash` must be supplied explicitly by the adapter. A missing value is quarantined rather than interpreted as zero.
- Split-adjusted OHLC may be entirely unavailable, but a partially populated adjusted bar is quarantined.
- Raw provider OHLCV values are copied without repair or coercive reinterpretation.
- Canonical structural/market-logic checks run after normalization. Their record-level worst quality state is attached to the resulting `DailyBar`.
- Duplicate canonical instrument/session observations are rejected by the quality layer.

Records that cannot be normalized are retained as machine-readable `NormalizationIssue` entries. They are not guessed, repaired, or silently dropped from the audit result. Subsequent completeness checks can therefore distinguish missing canonical coverage from apparently complete data.

This layer does not decide whether a provider's adjustment semantics are acceptable. That evidence belongs to provider evaluation and the provider adapter's capability/limitation declaration.
