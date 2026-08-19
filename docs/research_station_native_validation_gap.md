# Research Station native-validation gap

The Research Station Run control must never remain indefinitely at `Validating configuration…`.

Browser native constraint validation occurs before the form `submit` event. A submit-based diagnostic observer therefore cannot report an invalid field if the browser suppresses the submit event entirely. The Run action must explicitly call `form.reportValidity()` before `requestSubmit()`, surface the first invalid field in the existing diagnostic modal, and only then enter the normal Strategy Builder submit/compile pipeline.

This preserves suite and Research Brain behavior while making browser-side validation observable and deterministic.
