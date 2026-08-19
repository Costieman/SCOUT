# Research Station stability program

Status: active hardening phase.

The Research Station core operator path is treated as a compatibility contract:

`start -> load suite -> select/create brain -> edit configuration -> validate -> run -> persist experiment -> associate with brain -> rerun/iterate`

## P0 — merge blockers

1. **Operator-path regression guard.** Suites, Brains, validation diagnostics, Run handoff, persistence, and report provenance must remain present together in the assembled runtime.
2. **Runtime identity.** The browser and terminal must expose the current Git branch and short commit SHA so an operator can prove which checkout is running.
3. **Suite/schema contract.** Every suite advertised as READY must resolve to values accepted by the same Strategy Builder request/validation contract used for manual configurations. READY must never mean "loads but cannot run".
4. **Explicit failure.** No Run action may fail silently. Browser validation, custom validation, backend rejection, and failed experiment execution must produce actionable diagnostics.
5. **Reproducibility.** Successful runs must persist dataset version, code version, resolved configuration, experiment identity, and immutable result evidence.

## P1 — reliability hardening

6. **Single-source parameter contracts.** Remove duplicated min/max/step/default definitions where UI, suites, sweep controls, and backend validators can drift independently.
7. **Startup health checks.** Fail early when canonical data, reviewed identity evidence, experiment registry, Brain storage, or required runtime assets are unavailable.
8. **Suite catalog audit.** Exercise every built-in suite through load-only resolution and backend request construction; BLOCKED/PARTIAL suites must remain visibly non-executable.
9. **Brain lifecycle tests.** Cover discovery, selection, creation, persistence, experiment association, refresh, and navigation back to the Research Station.
10. **Duplicate-run semantics.** Fingerprinting must include every research-relevant parameter; warnings must never prevent an explicitly requested rerun.
11. **Report consistency checks.** Dataset/bar counts, event counts, provider-call claims, fingerprints, code version, and manifest metadata must agree before a successful report is presented.
12. **Structured diagnostics.** Preserve phase timings and machine-readable failure context so slow/failing runs can be traced without browser guesswork.

## P2 — safe performance

13. Cache immutable canonical reads only; never cache research conclusions or experiment manifests.
14. Bound caches and provide deterministic invalidation/restart behavior.
15. Profile first-run and neighboring-run phase timings before optimizing analytical loops.
16. Require result-equivalence tests for every performance optimization.
17. Optimize repeated indicator/event calculations only after the operator path and provenance checks remain green.

## P3 — strategy expansion gate

New indicators, suites, exits, and strategy families should resume only after P0 is green and P1 has automated coverage. Each newly completed strategy suite must ship with its own schema/launch regression case so expanding the top-20 catalog cannot destabilize existing suites.

## Stability scorecard

A change is mergeable only when all applicable checks are green:

- repository hygiene / formatting / lint / strict typing
- full automated test suite
- assembled Suite -> Brain -> Run runtime contract
- READY-suite schema compatibility
- successful-run persistence/provenance contract
- explicit failure-diagnostic contract
- performance result-equivalence checks when runtime behavior is optimized

The scorecard is intentionally conservative: a feature that is useful but breaks an established operator contract is a regression, not progress.
