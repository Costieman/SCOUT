# Legacy consolidation detector deprecation

`trade_scout.patterns.consolidation_breakout` is retained temporarily as a compatibility and shared-configuration module, but its event-producing surfaces are deprecated for production use.

The deprecated production surfaces are `ConsolidationBreakoutEvent`, `CurrentConsolidationState`, `detect_consolidation_breakouts`, and `current_consolidation_state`. New production code must use the typed Pattern & Event Engine under `trade_scout.events`, including `detect_consolidation_events`, `replay_consolidation_pipeline`, and the typed current projection.

`ConsolidationBreakoutConfig`, `TrendFilter`, `trend_qualified_indices`, and `required_trend_history_sessions` remain active shared research primitives until they are relocated independently. The legacy detector remains available to migration-equivalence tests so historical semantics can be compared explicitly rather than reconstructed from memory.

An architecture acceptance test prevents production modules from importing the deprecated event surfaces. This preserves one production event-generation path while retaining the old implementation only as a controlled compatibility oracle for migration evidence.
