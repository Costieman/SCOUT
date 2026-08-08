# Universe module

## Purpose

The universe module reconstructs which instruments were eligible on a historical date. It must not substitute today's survivors or current classifications for point-in-time state.

## Current contract

A universe decision consumes an `InstrumentRecord` plus explicitly dated eligibility measurements. The first implementation supports configurable exchange/security-type/quality gates, minimum price, trailing average dollar volume, and minimum trading-history requirements.

The caller must state the measurement date and canonical dataset version. A measurement dated after the requested historical `as_of` date fails rather than being used. Missing required measurements create explicit exclusion reasons rather than shortened windows, fills, or inferred eligibility.

Inactive/delisted instruments remain valid historical candidates before their delisting date. Ticker is not used as identity.

## Thresholds

The code does not establish USD 5 / USD 5 million as permanent rules. Those values are candidate Version 1 research baselines in the research-program specification and remain configurable until provider coverage is evaluated and the baseline is explicitly accepted.

## Non-responsibilities

This module does not calculate technical features, repair missing bars, infer current eligibility from historical outcomes, query provider-native data, or define a trading setup.
