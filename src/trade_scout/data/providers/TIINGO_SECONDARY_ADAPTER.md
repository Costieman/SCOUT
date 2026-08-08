# Tiingo secondary-validation candidate adapter

**Status:** evaluation implementation only - Tiingo is not an accepted secondary provider.

This adapter implements the first independent secondary-validation candidate behind the existing `ProviderAdapter` boundary. It is intentionally narrower than the canonical-provider adapter because the Phase 1 role is to supply independent raw OHLCV and corporate-action evidence for selected instruments and dates, not to become a second canonical source.

## Documented Tiingo behavior used here

The implementation was checked against Tiingo's official documentation on 8 August 2026:

- End-of-Day prices expose raw `open`, `high`, `low`, `close`, `volume`, `divCash`, and `splitFactor` fields.
- The same EOD response exposes `adjOpen`, `adjHigh`, `adjLow`, and `adjClose`, but Tiingo documents these adjusted values as incorporating both split and dividend adjustments using a CRSP-style methodology.
- Tiingo authentication can be supplied through an `Authorization: Token <token>` header rather than a URL parameter.
- Tiingo's current symbology documentation says delisted support exists where tickers have not yet been recycled, while permaTicker/delisted symbology continues to expand.
- Tiingo's utility search endpoint can expose active/delisted state and identity fields, but the endpoint is currently documented as early beta.
- Detailed split and distribution corporate-action endpoints are also documented as early-release/beta capabilities.

Official documentation reviewed:

- https://www.tiingo.com/documentation/end-of-day
- https://www.tiingo.com/documentation/general/connecting
- https://www.tiingo.com/documentation/appendix/symbology
- https://www.tiingo.com/documentation/utilities/search
- https://www.tiingo.com/documentation/corporate-actions/splits
- https://www.tiingo.com/documentation/corporate-actions/dividends

## Identity rule

The adapter never treats the Tiingo query ticker as permanent identity. Construction requires explicit `TiingoInstrumentLink` records pairing each query symbol with a previously established stable provider-side identity. A request for an unlinked symbol fails rather than inventing an identity.

The current adapter deliberately does not automate the search/beta symbology step. That remains part of the live Tiingo evaluation because the availability and meaning of `permaTicker`/OpenFIGI fields must be verified using the user's actual entitlement before they are admitted into the permanent instrument master.

## Price representation rule

Only raw Tiingo OHLCV is exposed through the Trade Scout daily-bar contract. Tiingo's `adj*` fields are **not** copied into Trade Scout's split-adjusted fields because Tiingo documents them as including dividend adjustments. Relabeling those values as split-adjusted executable prices would violate the Data Foundation adjustment policy.

The EOD `splitFactor` and `divCash` fields are preserved as provider evidence. Non-unit `splitFactor` and non-zero `divCash` observations also create provider-neutral validation corporate-action records. The current EOD factor cannot distinguish every detailed split/stock-distribution subtype, which remains an explicit limitation rather than being guessed.

## Deliberate non-capabilities

- No full security-master enumeration.
- No dated symbol-history reconstruction.
- No use of beta Search as a hidden production identity source.
- No use of Tiingo total-return adjusted OHLC as Trade Scout split-adjusted OHLC.
- No assumption that the current delisted-ticker coverage is sufficient for canonical survivor-bias control.
- No provider acceptance without a credential-backed sample and licensing review.

## Next evidence gate

Once a Tiingo API token is available, the secondary-provider evaluation should establish stable identity links for a small overlapping sample, retrieve the same instrument/date observations used in the Massive evaluation, and feed those records into Trade Scout's existing cross-provider reconciliation layer. Price and volume disagreements remain quality events; Tiingo values are validation evidence and are never averaged into the canonical primary feed.
