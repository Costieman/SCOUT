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

## Pattern-state integration

The consolidation Pattern/Event pathway uses the laboratory through the normal `ResearchBar` contract. The persistent lifecycle tracker fixes a pattern instance's formation interval and structural boundaries when it first qualifies; later sessions may move that same instance between `QUALIFIED` and `TRIGGER_READY`, invalidate it, or allow the Event layer to mark it `CONSUMED` after a confirmed breakout.

Lifecycle hardening follows the Pattern & Event Engine specification:

- nested durations remain independent pattern instances rather than being silently collapsed;
- event confirmation consumes an instance once, and a replacement instance must be formed wholly after the terminal session;
- reset/cooldown is expressed in trading-session updates rather than calendar time;
- data/eligibility failure, trend failure, support failure, range expansion, maximum age, and explicit corporate-action discontinuities are deterministic invalidation reasons;
- one incremental update path is used by historical batch replay and later scanner-style updates;
- one lifecycle cannot mix instruments, dataset versions, or price representations; and
- prefix replay is required to match the corresponding prefix of a longer replay, making future-bar leakage directly testable.

Corporate actions are supplied explicitly to the lifecycle pipeline. A material action terminates an active instance and prevents a subsequent rolling window from bridging the discontinuity; a new instance must form from bars strictly after the action date.

## Outcome-path integration

The next integration layer consumes the shared `EventRecord` contract rather than pattern-specific types. It measures next-session-open forward paths while preserving explicit truncation instead of silently deleting incomplete horizons.

The synthetic suite now verifies:

- a generated consolidation breakout flows through `EventRecord` into a complete outcome path;
- MAE/MFE values and their time-to-extreme session offsets are retained;
- an overnight gap-down is visible as both entry-gap and path-gap evidence;
- a stop-breach-and-recovery scenario remains an unmanaged path, proving the Outcome layer does not impose a stop rule; and
- a same-day high/low ambiguity is preserved through extreme-order state and drawdown bounds rather than resolved with invented intraday sequencing.

## Scientific use

The laboratory should be used as a controlled dependency for pattern/event integration, outcome-path measurement, risk-policy comparison, leakage tests, and replay verification. Tests should assert against scenario annotations rather than reverse-engineering the expected answer from the implementation under test.

The synthetic laboratory does not authorize promotion of a strategy and does not substitute for real-data validation. It isolates software and analytical-contract correctness from data-provider availability so those two sources of uncertainty can be reduced independently.
