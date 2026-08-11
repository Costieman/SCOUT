# Research-50 reviewed identity expansion v0.7

## Purpose

This review advances the fixed 50-stock exploratory research target from 18 to 42 reviewed Tiingo identities without changing the target into a historical S&P 500 claim. Acquisition, identity review, and canonical price promotion remain separate gates.

The private review probe reported all 32 acquired-but-unreviewed target series as structurally clean. Structural cleanliness is necessary but not sufficient for identity promotion, so each provider continuity series was still checked against explicit public issuer/ticker history.

## Advanced in v0.7

`CSCO`, `CVX`, `GE`, `GOOGL`, `GS`, `HD`, `JNJ`, `LLY`, `MA`, `MCD`, `META`, `MSFT`, `NEE`, `NFLX`, `NVDA`, `ORCL`, `PG`, `RTX`, `SCHW`, `TMUS`, `TSLA`, `UNH`, `V`, and `WMT`.

Important continuity boundaries are represented explicitly rather than relabelled silently: CHV -> CVX, GOOG -> GOOGL, FB -> META, FPL -> NEE, UTX -> RTX, PCS -> TMUS, Oracle's Nasdaq -> NYSE transfer, T-Mobile's NYSE -> Nasdaq transfer, and Walmart's 2025 NYSE -> Nasdaq transfer.

For long-lived unchanged issuers whose exact ticker inception predates the bounded research window, the reviewed symbol interval begins at the campaign lower bound `1996-01-02`; that date is a coverage assertion, not an IPO-date claim. McDonald's separately retains its sourced 1965 IPO date while the reviewed MCD symbol interval is bounded to the 1996+ research campaign.

## Primary-source examples

- Cisco investor FAQ: public since 1990-02-16 under CSCO.
- Chevron 2001 Form 10-K: CHV through 2001-10-09 and CVX beginning 2001-10-10.
- Google/Alphabet SEC filings: GOOG public history from 2004-08-19, Class A GOOGL from 2014-04-03, and the later Alphabet successor reorganization.
- Meta SEC filings: FB public history followed by META beginning 2022-06-09.
- NextEra newsroom: NYSE ticker changed from FPL to NEE at the start of trading on 2010-06-23.
- Netflix SEC filing: Nasdaq NFLX since the 2002-05-23 IPO.
- NVIDIA SEC filing: public trading began 1999-01-22 under NVDA.
- RTX/UTC SEC filing: former UTC common stock previously traded as UTX and began trading as RTX on 2020-04-03 after the Raytheon merger.
- MetroPCS/T-Mobile SEC filings: PCS began trading 2007-04-19; TMUS began 2013-05-01; TMUS moved from NYSE to Nasdaq on 2015-10-27.
- Tesla SEC filing: Nasdaq TSLA trading began 2010-06-29.
- Visa investor/SEC history: NYSE V began 2008-03-19.
- Walmart SEC filing: WMT remained the symbol when listing moved from NYSE after 2025-12-08 to Nasdaq on 2025-12-09.

Exact source URLs live with the corresponding checked-in seed intervals and lineage events.

## Deliberately deferred target symbols

Eight of the 50 remain outside reviewed identity scope:

- `BAC`: the provider series crosses the 1998 NationsBank/BankAmerica merger while the current issuer is the NationsBank successor; pre-merger ownership remains unresolved.
- `BKNG`: Tiingo begins 1999-03-31, after the sourced Priceline public-trading start on 1999-03-29.
- `COST`: Tiingo begins in 1996 while PriceCostco used PCCW before the 1997 transition to COST; the exact trading-date boundary is not yet established from an accepted primary source.
- `HON`: the current Honeywell registrant is the AlliedSignal legal survivor of the 1999 merger, while the provider HON history begins in 1996.
- `JPM`: the current JPMorgan Chase registrant descends through the Chemical/Chase legal survivor; ownership of the pre-combination provider JPM history remains unresolved.
- `MRK`: the 2009 Merck/Schering-Plough successor structure makes permanent-issuer ownership of the earlier provider MRK continuity series ambiguous without dedicated adjudication.
- `MS`: the current Morgan Stanley registrant is the Dean Witter legal successor from the 1997 combination; the provider MS series begins before that boundary.
- `XOM`: Exxon is the legal survivor of the 1999 Mobil merger, but the exact pre-merger Exxon ticker boundary needed to label the 1996 provider series has not yet been verified from an accepted primary source.

`ALGN` also remains a previously deferred non-target review case because Tiingo starts after the sourced first public-trading sessions.

## Safety boundary

This change is metadata-only. It makes no provider calls and promotes no price rows. The private operator must regenerate the v0.7 candidate against the durable profile before any immutable instrument-master or price promotion is attempted. Deferred ambiguity is preserved rather than inferred away.
