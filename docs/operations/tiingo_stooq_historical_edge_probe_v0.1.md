# Tiingo / Stooq historical edge probe v0.1

## Purpose

This probe asks whether the existing no-credential Stooq candidate supplies observations for the two
reviewed ALGN sessions that precede Tiingo's observed history start.

The reviewed edge is fixed:

- instrument: Align Technology (`ALGN` / Stooq query `ALGN.US`);
- exchange calendar: XNAS;
- reviewed lifecycle start: 2001-01-26;
- previously observed Tiingo first bar: 2001-01-30;
- expected gap sessions: 2001-01-26 and 2001-01-29;
- overlap anchor: 2001-01-30.

## Interpretation

The existing historical-edge classifier treats Tiingo as provider A and Stooq as provider B. A
`SECONDARY_CONFIRMS_PRIMARY_GAP` result requires Stooq-only observations on both reviewed gap dates
and exact raw-field agreement at the 2001-01-30 overlap anchor under the pinned tolerance.

A different result remains informative but does not establish a usable historical replacement. In
particular, Stooq's CSV adjustment semantics are still unaccepted. Date coverage or even one exact
anchor agreement is not sufficient to authorize canonical filling.

## Safety boundary

The workflow does not interpolate, average, vote across providers, modify provider acceptance, select
a serving source, or write canonical prices. Provider OHLCV remains in runner memory; the uploaded
artifact contains metadata and dates only.

`canonical_fill_allowed` is always false.

## GitHub operation

Run **Tiingo Stooq historical edge probe** from the Actions tab on `main`. It has no user inputs and
uses only the existing `TIINGO_API_TOKEN` repository secret. Stooq requires no credential.
