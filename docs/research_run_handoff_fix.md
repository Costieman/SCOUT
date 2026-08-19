# Research run handoff diagnostic fix

The Research Station v4 workflow intentionally calls `preventDefault()` after all client-side validators have passed, serializes the form, adds the execution markers, and navigates to the backend research URL. The v5 diagnostic observer previously interpreted any `defaultPrevented` submit as a validation failure, which meant a normal v4 handoff could be reported as a SCOUT validation-path bug.

The fix treats the existing `Request accepted — starting research…` dock state as an intentional successful v4 handoff. Genuine browser/composer/sweep cancellations still surface through the existing failure modal. No Strategy Suite, Research Brain, analytical definition, or backend research logic is changed.
