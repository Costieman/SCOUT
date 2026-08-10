# Tiingo durable profile in Data Health v0.1

## Purpose

The local operator console should surface the derived quality evidence produced by `profile-tiingo`
without exposing licensed Tiingo rows. The console remains read-only and does not call Tiingo.

When `<workspace>/evidence/tiingo-profile/profile.json` exists, Data Health reports:

- profiled symbol and row counts;
- structural anomaly symbol count;
- invalid/duplicate/non-monotonic date counts;
- missing required fields and invalid numeric rows;
- OHLC ordering and negative-volume violations;
- observed split and dividend event counts; and
- long calendar-gap screening observations.

The profile is checksum/provenance derived evidence, not a canonical dataset and not provider
acceptance. Unknown or absent profile evidence remains explicit rather than being treated as zero.
