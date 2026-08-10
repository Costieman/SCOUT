# Phase 1 low-fidelity application shell v0.1

## Decision

Implement the **application-facing contracts and low-fidelity wireframe now**, but defer a heavy
front-end framework and live analytical workflows until their upstream contracts are accepted.

This is deliberately narrower than implementing the Phase 7 Research UI. The dashboard
specification asks for low-fidelity wireframes as an immediate next decision, while the master
roadmap keeps the full Research Lab and experiment visualisation after the data, feature,
pattern/event, outcome/risk, and research-framework foundations.

## Why this slice is useful now

The interface can expose architectural mistakes early without allowing presentation work to reverse
the governing sequence: Research first, Validate second, Scan third, Alert last.

The current shell therefore makes Phase 1 failure/gating state first-class:

- Data Health is the default active workspace.
- Research Lab is visible as a preview but cannot launch while the data foundation is unaccepted.
- Scanner normal candidate rows are blocked until fresh canonical data and production-eligible
  strategy definitions exist.
- Alerts are present in navigation but disabled.
- No brokerage execution controls exist.

## Application contract boundary

`src/trade_scout/api/dashboard_contracts.py` defines provider-independent presentation objects for:

- provenance,
- provider/data health,
- Research Lab availability,
- evidence summaries,
- scanner candidate rows,
- scanner freshness gating,
- experiment-library rows, and
- one application snapshot.

These objects contain **already-computed state**. The UI must not calculate features, patterns,
events, stops, statistics, or ranks. Provider-native market payloads do not cross this boundary.

## Low-fidelity renderer

`src/trade_scout/app/low_fidelity.py` is a dependency-free HTML renderer. It is intentionally
replaceable and exists to test information architecture rather than select a permanent front-end
stack.

Navigation follows the conceptual workflow:

1. Research
2. Scanner
3. Experiments
4. Data Health
5. Alerts
6. System

The renderer includes a provenance disclosure on important analytical sections and uses explicit
text labels in addition to colour for PASS/WARN/QUARANTINE/BLOCKED states.

## Preview

Run:

```bash
uv run python scripts/render_trade_scout_ui_prototype.py
```

The generated file is:

```text
runtime/ui-prototype/index.html
```

The preview is explicitly labelled as a design fixture. It does not fabricate scanner candidates or
research results. Current provider descriptions are explanatory preview text only and are not live
health checks.

## Tests

The first UI-contract tests enforce that:

- launch cannot be enabled while blocking reasons remain,
- a blocked scanner cannot expose normal candidate rows,
- probability-like display values remain bounded,
- application snapshots are timestamped with timezone-aware values,
- required workspaces and provenance remain visible,
- failure/gating language is visible,
- user-facing text is escaped, and
- trade-execution controls are absent.

## Deferred deliberately

The following remain deferred until their upstream phase gates are ready:

- permanent front-end framework selection,
- live experiment launch/edit forms,
- parameter surfaces and research visualisations,
- candidate charting,
- live scanner filtering/ranking,
- alert configuration,
- authentication/multi-user state,
- broker/execution integration.

The next UI work should connect these contracts to real application services one workspace at a
time, beginning with Data Health after a durable canonical dataset/status service exists.
