# A+B data flow v0.1

`Alpha Vantage raw -> Alpha adapter -> provider bars`

`Stooq raw -> Stooq adapter -> provider bars`

`reviewed instrument links + provider bars -> composite evidence -> coverage/discrepancy report`

The composite report is not canonical storage. Promotion into canonical Parquet/DuckDB remains a separate reviewed step so the raw, evidence, and canonical layers cannot be confused.
