# Run failure modal acceptance

Acceptance behavior for the Research Station:

- Pressing **Run research** after a valid configuration must produce a request containing `run_attempt` and `execute_run=1`.
- If a composer, exit-sweep, entry-sweep, or native form validation rule cancels submission, a modal titled **Research did not start** must explain the available reason and state that nothing was sent to the backend.
- If the backend rejects a parsed Strategy Builder request with a handled configuration error, the returned reason must be surfaced automatically in the modal.
- Suite preview state (`load_only`) must never be included in an intentional execution request.
