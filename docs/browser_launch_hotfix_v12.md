# Research Workbench browser launch hotfix v12

The workbench previously called `webbrowser.open()` before the HTTP server had started accepting connections. On slower startup paths this could open a browser tab that failed to load and did not retry.

The launcher now starts a small daemon thread that polls the configured host/port and opens the Strategy Builder only after the listener accepts a TCP connection. The research server itself remains unchanged.
