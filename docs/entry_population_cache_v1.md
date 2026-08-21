# Frozen entry population cache v1

Strategy Builder entry-event membership is upstream of outcome and exit-policy evaluation. The cache identity therefore includes canonical dataset/version scope, research window, entry family and definition version, plus resolved entry parameters. It intentionally excludes stop, target, slippage, commission and other post-entry settings.

The cache is bounded and disposable. Canonical data, experiment manifests and event definitions remain authoritative. Cache failure or eviction may increase runtime but must never alter analytical meaning.
