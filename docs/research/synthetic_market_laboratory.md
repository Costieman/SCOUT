# Synthetic Market Laboratory

## Purpose

The synthetic market laboratory provides deterministic artificial market histories for end-to-end analytical verification before the real canonical dataset is required. The laboratory is not a simulator intended to reproduce the statistical distribution of real markets. Its purpose is controlled scientific testing: the embedded market behavior is known in advance, so downstream modules can be checked against explicit expected outcomes.

## Contract

Each `SyntheticMarketScenario` contains:

- a stable scenario identifier and registered scenario kind;
- vendor-independent `ResearchBar` records;
- immutable annotations describing the behavior intentionally embedded in the history;
- optional split-adjusted bars when a second price representation is scientifically relevant; and
- optional canonical corporate-action records.

The bars use the same `ResearchBar` contract consumed by downstream research modules. This prevents synthetic tests from exercising a parallel or simplified analytical interface.

## Initial canonical scenarios

The Version 1 laboratory contains ten controlled histories:

1. clean monotonic uptrend;
2. consolidation followed by confirmed breakout;
3. false breakout followed by immediate structural failure;
4. known missing expected trading sessions;
5. two-for-one split with raw discontinuity and continuous split-adjusted history;
6. isolated volatility and volume shock;
7. broad consolidation containing a tighter nested base;
8. deterministic overnight gap-down;
9. stop breach followed by later recovery; and
10. daily-bar ambiguity in which both stop and target are touched but intraday ordering is unknowable.

## Scientific use

The laboratory should be used as a controlled dependency for pattern/event integration, outcome-path measurement, risk-policy comparison, leakage tests, and replay verification. Tests should assert against scenario annotations rather than reverse-engineering the expected answer from the implementation under test.

The synthetic laboratory does not authorize promotion of a strategy and does not substitute for real-data validation. It isolates software and analytical-contract correctness from data-provider availability so those two sources of uncertainty can be reduced independently.
