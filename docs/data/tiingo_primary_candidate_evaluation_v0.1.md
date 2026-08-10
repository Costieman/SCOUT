# Tiingo primary-baseline candidate evaluation v0.1

## Purpose

This evaluation tests Tiingo as a possible free baseline provider without promoting it by enthusiasm or convenience. The governing rule remains **evidence before conviction** and the provider-specific acceptance rules remain those in the Data Provider Interface & Ingestion Specification.

## Acceptance mapping

The credential-backed runner checks the following evidence before any primary-provider decision:

- authentication and connectivity using a secret supplied only by the execution environment;
- reference metadata and advertised history bounds on multiple S&P 500 names;
- actual retrieval of 1996 daily data for multiple long-lived securities;
- current daily OHLCV plus raw/adjusted/corporate-action field shape;
- a known historical split window and a dividend-bearing year;
- repeat-request determinism on an identical bounded request;
- one inactive/delisted security retrieval probe;
- explicit licensing, identity/symbol-history, survivor-bias, normalization, rate/retry/checkpoint, and secondary-validation gates.

A passing HTTP/API probe is **not** sufficient for provider acceptance. The Trade Scout primary-adapter specification additionally requires reproducible historical backfill, correct stable identity/symbol mapping, characterized inactive/delisted coverage, corporate-action handling, tested rate/retry/checkpoint behavior, canonical normalization, secondary-source validation, deterministic daily updates, and successful downstream consumption.

## Licensed-data handling

Tiingo Starter is documented as internal-use-only. The GitHub live evaluation therefore uploads only a derived diagnostic report containing dates, counts, field-presence information and deterministic hashes. It does not upload raw licensed OHLCV rows and it never logs or serializes the API token.

## Current architectural blocker

The existing Tiingo adapter correctly refuses to label Tiingo's total-return adjusted OHLC as Trade Scout split-adjusted OHLC. It also leaves `ProviderDailyBar.split_factor` unset because Tiingo's EOD `splitFactor` is an event-date split ratio, while the Trade Scout provider contract requires a cumulative split-only price multiplier. This is a **visible blocker**, not a reason to silently reinterpret the field.

Before Tiingo can become the baseline canonical provider, Trade Scout must implement and test an explicit Tiingo corporate-action-to-cumulative-adjustment transformation using complete split history, then prove that transformation around known splits and through cross-provider reconciliation.

## Decision rule

- Transport/history/field failures: reject or pause Tiingo baseline evaluation.
- Transport/history/field success with unresolved required gates: keep Tiingo as a viable candidate, but `primary_provider_accepted=false`.
- Only after all mandatory provider-acceptance gates pass may an ADR promote Tiingo to primary/baseline status.

This implements the project principle that progress is reduction of uncertainty, not amount of code written.
