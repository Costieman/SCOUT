# Trade Scout private operator workspace v0.1

## Purpose

The operator workspace is the durable local root for Phase 1 research-data operations. It keeps
licensed/raw provider evidence outside the Git repository while giving acquisition, verification,
reconciliation evidence, canonical storage, and the Data Health console one shared location.

The workspace is intentionally private and local. The CLI refuses a workspace path inside the
SCOUT Git repository tree. `workspace.json` contains control metadata only and never stores API
keys, access tokens, raw market-data values, or credentials.

## Layout

After initialization the root has this shape:

```text
<workspace>/
  workspace.json
  providers/
    tiingo/
      raw/
      receipts/
      safe-state.json          # appears after campaign state is created
  evidence/
    composite/
    corporate-actions/
    failed-ingestion/
  canonical-store/
```

`providers/tiingo/raw/` contains licensed raw evidence and must remain private. Receipts contain
metadata/checksums only. A Tiingo symbol is not treated as durably complete unless its raw batch can
be re-read and verified against a receipt and the safe campaign state.

## Initialize once

Choose a directory **outside** the SCOUT checkout, for example:

```bash
WORKSPACE="$HOME/trade-scout-private"

uv run python scripts/trade_scout_workspace.py init \
  --root "$WORKSPACE" \
  --storage-namespace "local-private-workstation-v1"
```

The storage namespace is an operator-chosen stable label for this physical/private storage area. It
is embedded in durable receipts so receipts cannot silently be reused against another storage
namespace.

## Inspect and verify

Safe status, without reading or printing provider payload values:

```bash
uv run python scripts/trade_scout_workspace.py status --root "$WORKSPACE"
```

Checksum-verify all durable Tiingo receipts and their relationship to campaign state:

```bash
uv run python scripts/trade_scout_workspace.py verify --root "$WORKSPACE"
```

Verification fails when a campaign-state completion lacks a verified receipt, a receipt is not
represented in safe state, or a receipt/raw batch is missing or checksum-invalid. Acquisition is
blocked while this consistency gate is failing.

## Acquire a bounded Tiingo slice

The token is read from the process environment only. Do not put it in `workspace.json`, command-line
arguments, files committed to Git, or chat transcripts.

```bash
export TIINGO_API_TOKEN="...set locally, outside Git..."

uv run python scripts/trade_scout_workspace.py acquire-tiingo \
  --root "$WORKSPACE" \
  --max-symbols 1
```

The command reuses the existing durable Tiingo slice runner. Each successful symbol must pass:

1. exact raw-response persistence;
2. raw manifest/checksum validation;
3. metadata-only durable receipt creation;
4. receipt re-verification; and
5. safe campaign-state advancement.

HTTP 429 remains a provider throttle event and is not converted into a market-data gap. The next
run resumes from safe durable state.

## Open the console against the same workspace

```bash
uv run python scripts/trade_scout_workspace.py serve \
  --root "$WORKSPACE" \
  --open-browser
```

The default address is `http://127.0.0.1:8765/`. The console automatically reads:

- checked-in provider acceptance assessments;
- the workspace Tiingo safe campaign state, when present;
- `evidence/composite/*.json`;
- `evidence/corporate-actions/*.json`;
- files under `evidence/failed-ingestion/`; and
- the explicitly selected canonical dataset, when configured.

Raw Tiingo payload directories are never served by the console.

## Canonical/freshness selection

Canonical dataset and scanner-freshness selections remain explicit operator decisions. Configure
them only after the corresponding canonical dataset exists:

```bash
uv run python scripts/trade_scout_workspace.py configure \
  --root "$WORKSPACE" \
  --canonical-dataset-version DATASET_VERSION \
  --scanner-required-session 2026-08-07
```

The console will then resolve the selected dataset through the canonical-store boundary. Selecting a
dataset does not create or promote one.

## Fail-closed boundaries

The workspace layer does not call providers except through the existing explicit acquisition
command. It does not perform feature engineering, pattern detection, ranking, trading, or hidden
reconciliation. It does not average disagreements or fill absent sessions. It is an operator shell
around already-separated Phase 1 services and evidence.
