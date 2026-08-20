# Iterative strategic research v10

SCOUT may now convert a completed one-variable response surface into one bounded follow-up sweep. The operator must explicitly click **Run suggested next sweep**; the button changes only Section 5 and then uses the existing Strategy Builder submission path, so browser validation, Brain association, experiment recording, duplicate-run checks, and failure diagnostics remain in force.

The planner stops rather than repeatedly optimizing a least-bad historical value when the tested surface is both effectively flat and materially below the hold control. In that state SCOUT asks whether the managed exit buys a compensating downside benefit (for example P05, profit factor, holding time, or stop/target behavior) and otherwise recommends switching the research variable.

For non-terminal surfaces, boundary optima are extended outward and interior optima are re-tested at finer local resolution. Entry-indicator sweeps use the same iterative mechanism, with integer-safe steps for period parameters and decimal steps for Bollinger standard-deviation parameters.
