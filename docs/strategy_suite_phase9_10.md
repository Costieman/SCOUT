# Strategy Suite Phase 9-10

Phase 9 compares fixed strategy-suite configurations without forcing heterogeneous evidence into a single winner score. SCOUT reports transparent trade-offs across cost-adjusted expectancy, drawdown control, effective sample size, and validation stability. A suite is marked dominant only when it is no worse on every compared dimension and strictly better on at least one.

Phase 10 governs lifecycle advancement. The supported sequence is idea -> exploratory -> candidate -> validation -> validated -> production-eligible -> scanner. Advancement is limited to one stage at a time and remains a recommendation rather than an automatic mutation.

Promotion gates become progressively stricter. Candidate research requires positive cost-adjusted expectancy, comparator evidence, sufficient effective sample size, and a fully executable suite. Validation additionally requires a frozen validation plan. Validated status requires holdout, robustness, and transaction-cost evidence. Production eligibility additionally requires validation stability. Scanner eligibility additionally requires historical replay parity plus current data-quality and freshness gates.

Structural suites that remain PARTIAL or REQUIRES_PATTERN cannot be promoted as if a looser approximation had been tested. The validation layer remains responsible for producing validation evidence; this application-layer module only evaluates explicit evidence supplied to it and does not infer production eligibility on behalf of validation code.
