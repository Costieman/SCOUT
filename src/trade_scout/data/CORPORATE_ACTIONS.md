# Corporate-action canonical boundary

Provider corporate-action events are research inputs, not executable-price repairs. Trade Scout resolves each provider event through the permanent instrument master, preserves its source event identity and primitive source fields, and stores the resulting canonical record in an immutable versioned Parquet dataset.

Ticker is never used to resolve a corporate action to an instrument. If the provider identity is not linked in the canonical instrument master, the event remains explicitly unresolved. A provider event ID may not silently map to two canonical actions, and a corporate-action dataset version may not be reused with changed content or provenance.

Canonical corporate-action promotion records the primary provider, source raw batches, normalization definition, and exact instrument-master snapshot used for identity resolution. Logical and physical checksums are verified on load. This makes a future provider correction a new dataset-version event rather than an overwrite.

The corporate-action layer does not calculate adjusted prices, infer missing splits/dividends, claim that an action explains a market move, or feed feature/pattern logic directly. Price-jump diagnostics and adjustment-policy validation remain separate quality responsibilities.
