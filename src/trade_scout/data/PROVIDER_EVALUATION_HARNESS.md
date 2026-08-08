# Provider evaluation harness

`evaluate_provider_adapter` executes the same provider-neutral checks against any concrete `ProviderAdapter`. The harness exists to compare candidate providers through one implementation rather than embedding different scientific tests inside vendor-specific code.

For each targeted sample case, the manifest supplies an exact provider instrument identity and symbol, bounded historical date range, optional expected active/inactive state, required corporate-action families, and whether dated symbol history is required. The harness checks provider identity consistency, service health, declared capabilities, inactive/delisted support, exact instrument discovery, bounded daily retrieval, repeated-request equality, request scope, canonical normalization/quality, required corporate actions, and symbol-history retrieval where specified.

Passing the automated harness is deliberately **not** final provider acceptance. The report retains unresolved manual/external gates for licensing and storage rights, exact raw-payload preservation in the concrete transport path, provider correction behavior across retrieval times, and execution of the agreed real historical sample. `provider_accepted` therefore remains false while those gates are unresolved.

The integration fixture uses a fake provider only to prove that the evaluation machinery is reusable and deterministic. It is not evidence that any real provider meets the Trade Scout data standard. A concrete candidate adapter and credentials are required for the next evaluation step.
