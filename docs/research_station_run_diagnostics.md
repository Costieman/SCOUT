# Research Station run diagnostics

The Research Station must never fail silently when the operator presses **Run research**.

The final browser submit observer executes after the existing composer and sweep handlers. If one of those handlers cancels submission, SCOUT opens a diagnostic modal with the available validation reason and confirms that nothing reached the backend. If validation succeeds, SCOUT serializes the final form state explicitly, removes preview-only state, adds a run-attempt marker, and navigates to the normal governed Strategy Builder execution route.

When the backend rejects a parsed configuration using the normal Strategy Builder validation path, the returned error is surfaced immediately in the same diagnostic modal. The run-attempt marker also makes a request easy to identify in the local server log if an unexpected server exception produces a plain-text 500 response.
