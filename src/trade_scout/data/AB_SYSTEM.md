# A+B system contract

The A+B system is an evidence layer between provider ingestion and canonical promotion.

Inputs are independently captured Alpha Vantage and Stooq raw daily bars linked to a reviewed Trade Scout `instrument_id`. Output is a provider-neutral classification of every session observed by either source.

`BOTH_AGREE` is corroborated evidence and may be eligible for automatic promotion under a separately versioned canonicalization policy. `A_ONLY` and `B_ONLY` are candidate completeness gains but remain review-required. `BOTH_DISAGREE` is an unresolved quality event.

The system never averages providers, interpolates canonical history, or discards the losing observation. Provenance is retained in the evidence row and original raw stores.
