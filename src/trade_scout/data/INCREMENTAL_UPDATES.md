# Incremental canonical revisions

The daily update path must preserve the same scientific meaning as historical ingestion. Incremental processing therefore creates a candidate for a new immutable canonical dataset version; it never edits the parent dataset in place.

## Revision semantics

- A revision starts from exactly one parent dataset version and one canonical provider.
- Incoming normalized bars must already carry the proposed target dataset version and the same canonical provider identity.
- New instrument/session keys are appended.
- Existing keys may be replaced only when they are explicitly present in the incoming correction lookback and their date is on or after the configured correction-window start.
- Parent records absent from the incoming response are retained. Missing incoming data never means “delete historical record.”
- Duplicate incoming instrument/session keys fail rather than using last-write-wins behavior.
- Corrections outside the declared lookback fail explicitly.
- An incoming record identical to the parent market content is recorded as unchanged and does not, by itself, justify a new dataset version.
- The result is deterministically ordered and all carried-forward records are relabeled with the proposed target dataset version for subsequent immutable promotion.

The revision planner does not fetch provider data, choose the correction-lookback length, bypass quality checks, or promote the candidate. Provider-specific correction behavior remains an adapter/evaluation concern; the resulting revision must still pass the normal quality and canonical-storage promotion gates.
