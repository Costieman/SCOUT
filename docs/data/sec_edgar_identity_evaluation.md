# SEC EDGAR identity/reference evaluation

## Role in Trade Scout

SEC EDGAR is evaluated as a complementary issuer/reference-data source. It is not a market-price
provider and must not be treated as the sole source of security identity or point-in-time universe
membership.

The accepted public surfaces for this slice are:

- `company_tickers_exchange.json` for current CIK/name/ticker/exchange associations;
- `data.sec.gov/submissions/CIK##########.json` for issuer submission metadata, including current
  names, former names, tickers, and exchanges where present.

## Identity boundary

CIK is an SEC filer/entity identifier. It is not equivalent to a CRSP-style permanent security
identifier. One issuer can have multiple listed securities, classes, or tickers, and ticker
associations can change over time. Trade Scout therefore retains CIK as issuer-level provenance and
must resolve canonical `instrument_id` independently.

The adapter intentionally refuses historical `as_of` instrument requests because SEC's current
association file is not a point-in-time universe history. Projecting it backward would violate the
Phase 1 survivorship-bias controls.

## Configuration

Automated SEC requests require a declared user agent. Configure:

```text
SEC_EDGAR_USER_AGENT=Trade Scout your-contact@example.com
```

This is configuration, not a secret. No EDGAR API key is required for these public data APIs.

## Current acceptance status

**Accepted only as a candidate complementary identity/reference source.**

The following remain outside this slice:

- permanent security identity resolution;
- complete historical ticker/symbol assignment;
- point-in-time listed-universe reconstruction;
- daily OHLCV;
- accepted corporate-action event feeds;
- automated reconciliation between SEC issuer identity and Alpha Vantage securities.

The next integration step is to reconcile SEC CIK-level issuer metadata with Alpha Vantage
point-in-time listing rows while retaining explicit ambiguity states for one-to-many mappings.
