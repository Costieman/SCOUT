# Research Program Dependency Planner

## Purpose

The first research-program templates define the scientific meaning and search space of Experiments A-J. The dependency planner adds a separate fail-closed question before execution: **are the exact resources needed by this experiment actually available now?**

This implements the project rule that configuration and dependencies are validated before execution, exclusions are counted rather than silently disappearing, and missing scientific inputs are never replaced with guessed defaults.

## Dependency families

The planner checks the selected experiment against an immutable `ResearchDependencyInventory` containing:

- exact canonical dataset versions;
- exact point-in-time universe versions;
- feature definitions;
- event definitions;
- prespecified outcome horizons;
- risk-policy identifiers;
- comparator definitions;
- validation-plan requirements;
- explicitly accepted research-integrity assumptions;
- analytical capabilities; and
- completed prerequisite experiments.

The inventory is deliberately declarative. The planner does not infer that a resource exists because a similarly named module exists, and it does not substitute a newer dataset, a different comparator, or a nearby horizon.

## Integration with the A-J templates

`preflight_first_program_dependencies()` first runs the scientific template dry run from the executable A-J template layer. Template blockers therefore remain authoritative for unresolved threshold families, prior experiment sequencing, frozen confirmatory inputs, and final-holdout reuse.

The dependency layer then materializes concrete requirements for the same experiment. Examples include:

- Experiment A: exact dataset/universe, T0-T6 trend capability, the declared 5/10/20/40/60/120/252-session horizons, and the unconditional eligible-universe comparator;
- Experiments B-E: the required consolidation/breakout event definitions and the corresponding trend, compression, ATR, or volume features;
- Experiments F-G: market-regime, volatility, VIX, and trading-age inputs;
- Experiment H: the frozen event set plus no-stop, fixed-percentage, ATR, structural, and hybrid policy definitions;
- Experiment I: the frozen primary horizon, comparator, selected risk policies, unseen-validation requirements, and predeclared robustness requirements; and
- Experiment J: walk-forward, final-holdout, nearby-parameter, higher-cost, and promotion-decision requirements.

## Research-integrity assumptions

Every experiment requires explicit acknowledgement of the governing no-lookahead, point-in-time eligibility, rule-based exclusion, and entry-convention assumptions. Risk and validation stages additionally require an explicit cost model before results can be interpreted as tradable evidence.

These are dependency records, not optimization parameters. They exist so a run cannot silently proceed under an unstated analytical convention.

## Output contract

`ResearchProgramDependencyPreflight` records:

- the scientific template dry run;
- every materialized dependency requirement;
- one pass/fail check per requirement;
- explicit blockers;
- a checksum of the requirement set; and
- a checksum of the supplied dependency inventory.

The checksums allow an operator or later application service to show that the same experiment was preflighted against the same declared resource state.

## Failure behavior

A missing dependency produces a blocker such as `missing feature: atr_14` or `missing validation_plan: final_holdout_reserved`. The experiment is not marked ready.

The planner does not:

- download or repair data;
- calculate a missing feature;
- create an event definition;
- invent an unresolved threshold;
- choose a substitute comparator or horizon;
- weaken a validation plan; or
- mark a prerequisite experiment complete.

Those actions belong to the relevant data, feature, event, experiment, or validation modules.

## Scientific boundary

Passing dependency preflight means that the declared experiment is structurally executable. It does **not** mean that the experiment has been run, that the evidence is positive, or that any rule is validated or production eligible.

The next layer can use this preflight artifact as the execution gate for a reproducible research run and later include it in the research evidence package.
