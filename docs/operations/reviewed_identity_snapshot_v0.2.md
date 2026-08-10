# Reviewed identity snapshot candidate v0.2

## Purpose

Version 0.2 closes the two predecessor-history gaps deliberately left unresolved by the v0.1
reviewed seed set. It does so only where primary-source evidence establishes both the historical
symbol and the relevant boundary dates.

The v0.1 seed file remains checked in as the fail-closed baseline. The operator command now defaults
to:

```text
configs/tiingo_reviewed_identity_seeds_v0.2.json
```

## Reviewed predecessor intervals

### Aptiv / Delphi Automotive

The reviewed interval is:

```text
DLPH  2011-11-17 through 2017-12-04
APTV  2017-12-05 onward
```

Evidence:

- an SEC-filed Delphi Automotive prospectus states that the ordinary shares had been publicly traded
  since 2011-11-17, when they were listed and began trading on the NYSE, and identifies the NYSE
  symbol as DLPH; and
- Aptiv's 2017 spin-off announcement states that Delphi Automotive ordinary shares would continue
  regular-way trading under DLPH through the distribution date and that the remaining company would
  change its symbol to APTV beginning 2017-12-05.

### Axon / TASER International

The reviewed interval is:

```text
TASR  2001-06-07 through 2017-04-05
AAXN  2017-04-06 through 2021-01-25
AXON  2021-01-26 onward
```

Evidence:

- TASER International's SEC-filed annual report states that its common stock began trading separately
  on Nasdaq under TASR on 2001-06-07 after an initial unit-trading period; and
- Axon's 2017 announcement states that the new AAXN ticker became effective at the Nasdaq open on
  2017-04-06. The previously reviewed 2021 announcement establishes the AAXN-to-AXON boundary.

## What `promotion_ready` means

With the local lineage audit whose observed starts are APTV 2011-11-17, AXON 2001-06-07, and ALLE
2013-11-18, v0.2 should have no identity coverage gaps. Therefore `promotion_ready` can be true for
this **three-instrument reviewed seed scope**.

That flag is deliberately not a campaign-wide readiness claim. It does not mean that all 52 acquired
Tiingo series, the full current S&P 500 snapshot, or a point-in-time historical universe has complete
reviewed identity coverage. The operator summary prints `promotion_scope: reviewed_seed_set_only` to
make that boundary explicit.

## Operator command

After pulling the v0.2 configuration, rerun:

```powershell
uv run python .\scripts\trade_scout_workspace.py build-tiingo-identity --root "$HOME\trade-scout-private"
```

The command makes no provider calls and does not promote price rows. It overwrites only the private,
metadata-only candidate artifact under:

```text
<workspace>/evidence/instrument-identity/tiingo-reviewed-candidate.json
```

The next step after a clean v0.2 candidate is a separate immutable instrument-master promotion step.
Price normalization should remain blocked until that snapshot promotion is explicit and versioned.
