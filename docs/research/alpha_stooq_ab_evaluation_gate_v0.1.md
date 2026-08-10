# Alpha Vantage + Stooq A+B evaluation gate v0.1

Structural implementation does not establish that either provider is historically correct or complete.

Before enabling canonical promotion beyond corroborated `BOTH_AGREE` rows, the live evidence campaign must answer:

1. How often do Alpha Vantage and Stooq agree for ordinary active securities?
2. What fraction of the union is `A_ONLY` or `B_ONLY`?
3. Are one-sided sessions explained by calendars, listing state, symbol identity, or true provider absence?
4. Where do OHLC fields disagree, and are disagreements concentrated around corporate actions?
5. Does volume require a different tolerance or representation policy from price?
6. Do known split periods behave consistently with the separately documented Stooq split semantics?
7. Can inactive/delisted cases be linked without ticker-only identity assumptions?

A one-sided observation is a candidate completeness gain, not an automatic canonical fill. Acceptance requires explicit evidence that the observation represents the intended instrument/session and price representation.
