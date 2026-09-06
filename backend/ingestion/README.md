# Offline ingestion

Runtime API handlers never download data. Both scripts below are manual,
ahead-of-time utilities for confirmed sources.

## Iceberg tracks (BYU/NIC v8.0)

    python -m backend.ingestion.iceberg_tracks --download
    python -m backend.ingestion.train_iceberg_model

## Sea ice (NOAA/NSIDC CDR G02202 v6)

    python -m backend.ingestion.fetch_seaice --download --date 2023-07-15
    python -m backend.data.build_real_scenario --date 2023-07-15

No Earthdata Login is required for the sea-ice mirror used here
(noaadata.apps.nsidc.org) -- verified directly. Both pipelines write files
that are gitignored (no explicit redistribution licence for a derived
subset was located for either source), so each machine runs its acquisition
step once while online; everything after that is offline.
