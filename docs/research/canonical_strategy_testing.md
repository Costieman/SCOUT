# Canonical Strategy Testing Workbench

**Status:** exploratory research interface  
**Data boundary:** immutable canonical datasets only  
**Provider calls:** none

## Purpose

This is the operator path for trying research ideas against Trade Scout's already-canonical market data without creating a parallel backtest stack or calling a market-data provider.

The workbench has two complementary entry points:

1. the existing browser research console for consolidation, multi-timeframe universe research, and risk research; and
2. the generic feature-expression strategy runner for ad hoc cross-sectional strategy tests.

Results from both paths remain exploratory. They are not validation, production eligibility, or a portfolio-capital backtest.

## Update the local repository

From the SCOUT repository in PowerShell:

```powershell
git checkout main
git pull
uv sync --dev
```

Use the private operator workspace root that already contains the selected canonical dataset and Trade Scout evidence. The examples below call it `<WORKSPACE_ROOT>`.

## Browser research console

Start the existing read-only research workbench:

```powershell
uv run python scripts/serve_research_workbench.py --root "<WORKSPACE_ROOT>" --open-browser
```

The console exposes the existing canonical-data research surfaces, including:

- `/research/universe` — market-wide consolidation research with daily, 2-session, 3-session, and weekly pattern timeframes;
- `/research/edge` — single-stock consolidation/edge exploration; and
- `/research/risk` — exploratory stop/risk research.

The application loads the selected immutable canonical dataset from the operator workspace. It does not fetch prices from Tiingo or another provider.

## Generic strategy runner

List the currently registered features:

```powershell
uv run python scripts/run_strategy_research.py --root "<WORKSPACE_ROOT>" --list-features
```

The current feature-expression set is:

- `return_5`
- `return_20`
- `return_252`
- `realized_volatility_20`
- `relative_volume_20`
- `atr_pct_14`
- `distance_sma_50_pct`
- `distance_sma_200_pct`

Run a simple momentum, relative-volume, and trend condition across the reviewed canonical cohort:

```powershell
uv run python scripts/run_strategy_research.py `
  --root "<WORKSPACE_ROOT>" `
  --strategy-id "momentum-rvol-trend-test-v0.1" `
  --name "Momentum RVOL Trend Test" `
  --expression "return_20 >= 0.05 and relative_volume_20 >= 1.5 and distance_sma_200_pct > 0" `
  --rank-feature return_20 `
  --limit 25 `
  --horizons 5,20,60
```

The runner forms signals using only features available as of each historical session, ranks qualifying instruments independently within that session, and measures post-signal paths through the canonical OutcomePath engine using next-session-open entry.

## Restrict a test to selected symbols

When the reviewed identity candidate is available in the operator workspace, a run can be limited to selected reviewed symbols:

```powershell
uv run python scripts/run_strategy_research.py `
  --root "<WORKSPACE_ROOT>" `
  --symbols AAPL,MSFT,NVDA `
  --expression "return_20 > 0 and distance_sma_200_pct > 0" `
  --rank-feature return_20 `
  --limit 3 `
  --horizons 5,20,60
```

## Restrict the historical signal window

Use `--start` and `--end` to control the sessions on which new signals may be formed:

```powershell
uv run python scripts/run_strategy_research.py `
  --root "<WORKSPACE_ROOT>" `
  --start 2018-01-01 `
  --end 2024-12-31 `
  --expression "return_252 > 0 and realized_volatility_20 < 0.30 and distance_sma_200_pct > 0" `
  --rank-feature return_252 `
  --limit 25 `
  --horizons 5,20,60,120
```

## Output

Each strategy run writes a checksummed JSON research artifact under the private workspace:

```text
evidence/research-strategies/
```

The terminal summary reports the canonical dataset version, feature-set version, instrument count, selected signal count, outcome horizons, descriptive horizon summaries, checksum, and output path. `provider_calls_made` is recorded as `false`.

## Interpretation boundary

The generic runner evaluates the canonical instrument cohort supplied to it. It does **not** silently claim that this cohort is historical S&P 500 membership, does not invent survivorship-bias corrections, and does not promote a positive exploratory result to a validated strategy.

The intended progression remains:

```text
canonical data -> exploratory research -> governed validation -> evidence-backed decision -> scanner/replay
```

For the first formal Consolidation Breakouts research program, use the governed Experiment A-J machinery rather than treating ad hoc workbench runs as substitutes for the registered program.
