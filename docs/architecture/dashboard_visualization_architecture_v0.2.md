# Trade Scout Dashboard & Visualization Architecture v0.2

Status: **design/contract implementation**  
Night-work package: **Night 1 — Dashboard and visualization architecture**

## Purpose

This package turns the accepted Dashboard, Visualization & User Workflow Specification v0.1 into a framework-neutral application blueprint that can be inspected and tested before a final front-end framework is selected.

The governing boundary is unchanged:

> The dashboard is a client of application/API contracts. It must not retrieve provider-native data or calculate features, patterns, events, outcomes, stops, statistics, or ranking scores.

The existing Phase 1 read-only console remains valid. This package adds a broader Version 1 design contract around it rather than pretending unavailable downstream research outputs already exist.

## Primary navigation

The Version 1 information architecture is fixed at the user-workflow level:

1. **Research Lab** — configure and inspect reproducible experiments.
2. **Market Scanner** — inspect current validated candidate states.
3. **Candidate Detail** — explain one current structure, historical evidence, and risk.
4. **Experiment Library** — search, compare, reproduce, and trace experiments.
5. **Data Health** — inspect data freshness, quality, provider state, and review work.
6. **Alerts** — configure communication preferences for approved scanner transitions.
7. **System / Project** — inspect build, versions, documentation, and project gates.

Low-level engines remain implementation modules rather than top-level pages.

## Analytical state versus display state

This package makes the separation machine-readable through `ControlBindingKind`.

### Analytical configuration controls

Research controls bind only to `config.*` paths. They must pass validated configuration and require a full resolved-configuration review before an experiment can launch.

Examples:

- strategy family -> `config.patterns.family`
- canonical dataset -> `config.data.dataset_version`
- universe -> `config.universe`
- outcome horizons -> `config.outcomes.horizons`
- risk policy -> `config.risk.policy`
- validation design -> `config.validation`

A front end may choose a dropdown, slider, multi-select, or another widget later, but the widget is presentation. The source of analytical truth is the validated configuration model.

### Display-only controls

Scanner filters, search boxes, chart ranges, chart overlays, and experiment-library search state bind only to `ui.*` paths. They may change what is visible; they cannot modify strategy eligibility, evidence cohorts, experiment membership, or stored analytical outputs.

`filter_scanner_candidates()` exists solely as a small executable proof of that boundary: it returns a presentation subset of immutable `ScannerCandidateSummary` contracts.

## Application/API consumption map

| Workspace | Primary contracts |
| --- | --- |
| Research Lab | `ResearchLabSummary`, `ResolvedExperimentConfiguration`, `ExperimentResultsView`, `ProvenanceSummary` |
| Market Scanner | `ScannerSummary`, `ScannerCandidateSummary`, `ProvenanceSummary` |
| Candidate Detail | `CandidateDetailView`, `PriceChartView`, `EvidenceProfileView`, `RiskSummaryView`, `ProvenanceSummary` |
| Experiment Library | `ExperimentSummary`, `ExperimentComparisonView`, `ExperimentManifestView`, `ProvenanceSummary` |
| Data Health | `DataHealthSummary`, `ProviderHealthSummary`, `ProvenanceSummary` |
| Alerts | `AlertRuleView`, `AlertHistoryView`, `ProvenanceSummary` |
| System / Project | `SystemProjectView`, `ProvenanceSummary` |

Some downstream contracts are names in the blueprint rather than implemented domain objects today. That is deliberate: the UI architecture states what must eventually be supplied without fabricating the underlying analytical layer.

## Chart contract catalogue

Every chart is described by a `ChartSpec` with:

- stable chart ID;
- chart family;
- source application contract;
- explicit required fields;
- x/y semantics;
- empty-state text;
- provenance requirement;
- an explicit canonical-price-basis flag where relevant.

### Research Lab

- Forward-return distribution.
- Outcome evidence by horizon.
- Parameter surface.
- Parameter-cell sample-size surface.

The sample-size surface is deliberately paired with the performance surface so an isolated attractive cell cannot visually hide weak support.

### Candidate Detail

- Canonical candlestick/current-structure chart.
- Comparable-event MAE versus MFE.
- Comparable forward-outcome distribution.

The price chart explicitly requires the declared canonical price representation used by the analysis. Chart geometry must not silently use a different adjusted series.

### Experiment Library

- Time-ordered validation-fold performance.

### Data Health

- Operational data-health status timeline.

The remaining workspaces initially use tables/status components rather than inventing charts merely for visual richness.

## Low-fidelity wireframes

### Research Lab

```text
+-----------------------------------------------------------------------+
| Research Lab                                      EXPLORATORY/VALIDATING|
+-------------------------------+---------------------------------------+
| Configuration                 | Resolved configuration / diff         |
| strategy family               | dataset + universe                    |
| dataset + universe            | feature/pattern/event versions        |
| outcome horizons              | risk/cost/validation                  |
| risk + validation             | [review before launch]                |
+-------------------------------+---------------------------------------+
| Results overview: N | uncertainty | expectancy | MAE/MFE | status       |
+-------------------------------+---------------------------------------+
| Forward return distribution   | Outcomes by horizon                   |
+-------------------------------+---------------------------------------+
| Parameter surface             | Matching sample-size surface          |
+-------------------------------+---------------------------------------+
| Robustness + provenance                                               |
+-----------------------------------------------------------------------+
```

### Market Scanner

```text
+-----------------------------------------------------------------------+
| Market Scanner                  freshness PASS/WARN/BLOCKED            |
+-----------------------------------------------------------------------+
| DISPLAY FILTERS: state | search | sort | sector/regime (later)        |
+-----------------------------------------------------------------------+
| Symbol | State | Base | Distance | Historical N | Evidence | Freshness|
| ...                                                                   |
+-----------------------------------------------------------------------+
| Filters change this table only. Strategy/evidence definitions fixed.  |
+-----------------------------------------------------------------------+
```

### Candidate Detail

```text
+-----------------------------------------------------------------------+
| SYMBOL | state | strategy version | as-of | freshness                 |
+-------------------------------------------+---------------------------+
| Canonical candlestick + structure         | Why it qualifies          |
| moving averages / boundaries / markers    | current feature snapshot  |
+-------------------------------------------+---------------------------+
| Comparable forward outcomes               | MAE vs MFE                 |
+-------------------------------------------+---------------------------+
| Validated risk summary                     | Cohort + uncertainty       |
+-----------------------------------------------------------------------+
| Provenance: data -> features -> pattern/event -> evidence/risk        |
+-----------------------------------------------------------------------+
```

### Experiment Library

```text
+-----------------------------------------------------------------------+
| Search / status filters                                               |
+-----------------------------------------------------------------------+
| Experiment | state | dataset | code | parent | decision               |
+-----------------------------------------------------------------------+
| Compare: configuration diff | fold results | outcome/risk differences |
+-----------------------------------------------------------------------+
| Reproduce from immutable manifest                                     |
+-----------------------------------------------------------------------+
```

## Synthetic preview

Run:

```powershell
uv run python .\scripts\render_dashboard_design_preview.py
```

The command writes `runtime/dashboard-design-preview/index.html`. It does not read the private workspace, call providers, run experiments, or consume licensed data.

The preview intentionally contains synthetic candidate names and synthetic evidence values. Those values exist only to make spacing, hierarchy, evidence language, and display filtering inspectable.

## Testing and acceptance evidence

The Night 1 package tests that:

- all seven workspaces exist exactly once in primary navigation;
- routes and workspace IDs are unique;
- all dashboard workspaces reject analytical logic;
- analytical controls must bind to validated `config.*` paths;
- display controls remain `ui.*` state;
- candidate charting requires a canonical price basis;
- scanner display filtering does not mutate candidate/evidence contracts;
- wireframes expose all primary workspaces and chart IDs;
- the preview contains no trade-execution controls.

## Explicit non-goals

This package does **not**:

- select a final JavaScript/front-end framework;
- implement experiment execution;
- implement Pattern/Event/Outcome/Risk calculations;
- create production-eligible scanner candidates;
- calculate a ranking score;
- call a provider;
- expose licensed/private market data;
- enable alert delivery;
- place or simulate brokerage orders.

## Follow-on dependencies

The blueprint deliberately names downstream application contracts that should be filled in as later Night Work packages produce their domain engines. This lets the UI remain stable while analytical capabilities arrive behind explicit interfaces.

The next scheduled Night Work package is the Pattern & Event Engine foundation. It should implement analytical contracts independently; the dashboard will consume those contracts later rather than reimplement their logic.
