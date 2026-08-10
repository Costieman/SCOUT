# A+B credential boundary v0.1

Alpha Vantage credentials are read only from the `ALPHA_VANTAGE_API_KEY` environment/repository secret. Stooq's current bounded CSV route requires no secret. Credentials are never written to reports, raw request metadata, Git-tracked configuration, or workflow artifacts.
