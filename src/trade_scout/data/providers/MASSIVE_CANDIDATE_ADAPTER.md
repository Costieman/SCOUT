# Massive candidate adapter

**Status:** evaluation implementation only — Massive is not an accepted canonical provider.

This adapter implements the current Phase 1 primary-provider candidate behind the existing `ProviderAdapter` boundary. It is based on the Massive Stocks REST documentation reviewed on 8 August 2026 and is deliberately limited to the evidence required for provider evaluation.

## Implemented mapping

- All Tickers (`/v3/reference/tickers`) is used for point-in-time common-stock reference records. The adapter requests both active and inactive records and admits an instrument only when a composite FIGI or share-class FIGI is available as a non-ticker provider identity.
- Daily aggregates (`/v2/aggs/ticker/.../range/1/day/...`) are requested in both unadjusted and split-adjusted form. Timestamps must match exactly. Raw OHLCV are preserved from the unadjusted response; split-adjusted OHLC are preserved from the adjusted response; the per-observation split factor is the explicit adjusted-close/raw-close ratio.
- Cash-dividend events (`/stocks/v1/dividends`) are attached to the ex-dividend session using the original `cash_amount` field.
- Splits (`/stocks/v1/splits`) and cash dividends are mapped to provider-neutral corporate-action records while retaining Massive event IDs and primitive source fields.
- Ticker Events (`/vX/reference/tickers/{id}/events`) is queried by stable FIGI rather than ticker to construct dated symbol history. Massive currently documents this endpoint as experimental, so that limitation is exposed in the capability declaration.
- All pagination URLs are restricted to `https://api.massive.com`; an external-host `next_url` is rejected.

## Raw preservation and credentials

`MassiveHttpClient` adds the API key only to the outgoing HTTPS query and never passes it to raw-manifest metadata. When `raw_root` is configured, exact response bytes are written through the existing immutable `RawBatchStore` before JSON decoding. API credentials are constructor inputs supplied by the runtime/secret environment; they are not committed to Git, configuration snapshots, or manifests.

## Deliberate limitations

- `first_trade_date` remains unset because the All Tickers response used by this adapter does not provide it. The final data foundation must derive/validate the first reliable trading date from approved provider evidence rather than invent one.
- A ticker/date lookup that resolves to zero or multiple stable FIGIs fails. The adapter never falls back to ticker-as-identity.
- Daily-bar retrieval requires explicit symbols. Long-run backfill orchestration and batching remain separate from the adapter.
- The candidate adapter does not establish that Massive licensing permits the intended Trade Scout deployment, that historical corrections behave acceptably, or that the real inactive/delisted/corporate-action sample passes. Those remain provider-acceptance gates.

## Official documentation reviewed

- https://massive.com/docs/rest/stocks/tickers/all-tickers
- https://massive.com/docs/rest/stocks/aggregates/custom-bars
- https://massive.com/docs/rest/stocks/corporate-actions/splits
- https://massive.com/docs/rest/stocks/corporate-actions/dividends
- https://massive.com/docs/rest/stocks/corporate-actions/ticker-events

The implementation must be rechecked against current Massive documentation before a future adapter version changes endpoint semantics.
