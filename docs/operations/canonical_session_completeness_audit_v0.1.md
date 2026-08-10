# Canonical expected-session completeness audit v0.1

## Purpose

This gate replaces the earlier heuristic of looking only for long calendar gaps with an explicit
expected-session comparison for reviewed U.S. equities. It answers a narrower and more defensible
question: between the beginning of an instrument's auditable history and the canonical dataset end,
does every expected full-day exchange session have exactly one canonical daily bar?

The audit never interpolates, forward-fills, synthesizes, or repairs a missing bar. A missing expected
session remains a data defect until evidence explains it.

## Calendar definition

Calendar version: `us-equities-core-full-day-v0.1`.

Supported listing exchanges in this version:

- `XNYS` — New York Stock Exchange;
- `XNAS` — Nasdaq Stock Market.

The recurring full-day closure rules cover New Year's Day, Martin Luther King Jr. Day, Washington's
Birthday, Good Friday, Memorial Day, Juneteenth from 2022 onward, Independence Day, Labor Day,
Thanksgiving Day, and Christmas Day. Early-close sessions remain expected sessions because a daily
bar should still exist.

New Year's Day follows the exchange-specific convention that a Saturday January 1 does not move the
full-day market closure back to Friday December 31. A Sunday January 1 is observed on Monday January
2.

The calendar also pins exceptional full-day closures needed by the current 2001+ reviewed history:

- September 11-14, 2001 after the September 11 attacks;
- June 11, 2004, national day of mourning for President Ronald Reagan;
- January 2, 2007, national day of mourning for President Gerald Ford;
- October 29-30, 2012, Hurricane Sandy;
- December 5, 2018, national day of mourning for President George H.W. Bush;
- January 9, 2025, national day of mourning for President Jimmy Carter.

Primary evidence is embedded with the calendar definition. The recurring holiday reference is the
NYSE trading-hours calendar. Exceptional closure evidence uses SEC or Nasdaq market notices.

## Audit range semantics

For each permanent instrument identity:

1. if `first_trade_date` is explicitly reviewed, the expected range starts there;
2. otherwise the expected range starts at the first observed canonical bar;
3. an active instrument is expected through the canonical dataset's own final trade date;
4. a delisted instrument is expected only through its recorded delisting date.

This deliberately does **not** claim that a provider's first observed bar proves the security's true
listing inception when `first_trade_date` is still unknown. Identity/listing-history review remains a
separate Phase 1 responsibility.

The audit reports four fail-closed defect classes:

- missing instrument history;
- missing expected exchange sessions;
- unexpected observed dates, such as a bar on a full-day closure or outside a reviewed lifecycle;
- duplicate observed dates.

A legitimate security-specific full-day halt would therefore fail this gate until separately reviewed
evidence justifies an explicit exception. The audit never silently treats a missing bar as a halt.

## Canonical promotion integration

Reviewed Tiingo canonical promotion now runs this audit before immutable price registration. Any
missing expected session, unexpected observed date, duplicate date, missing instrument history, or
unsupported exchange blocks promotion.

This does not change Tiingo provider acceptance and does not select a serving dataset.

## Local audit of an already-promoted snapshot

From the repository root:

```powershell
uv run python .\scripts\audit_canonical_session_completeness.py --root "$HOME\trade-scout-private"
```

The command defaults to `tiingo-reviewed-split-only-v0.2`. A different immutable canonical dataset can
be supplied explicitly with `--dataset-version`.

The command performs no provider calls. It writes metadata-only evidence under:

```text
<workspace>/evidence/session-completeness/
  <dataset-version>__us-equities-core-full-day-v0.1.json
```

The report contains dates, counts, identity references, and checksums, but no OHLCV values. It exits
zero only when the audited canonical dataset is complete under the pinned calendar definition.

## Scope boundary

A passing report proves expected-session coverage only over the audited canonical range. It does not
prove point-in-time S&P 500 membership, delisting completeness, provider licensing/acceptance,
secondary-provider agreement, or that the first observed provider bar is the true first listing date
when the instrument master does not yet contain a reviewed `first_trade_date`.
