# ICE-NAV methodology and evidence boundaries

## Iceberg observations

The confirmed source is the **BYU/NIC Consolidated Antarctic Iceberg Tracking
Database v8.0**, distributed as per-iceberg CSV files in a ZIP archive without
registration or an API key. Coordinates are decimal degrees and dates use
`YYYYDDD`. Required citation:

J.S. Budge and D.G. Long, "A comprehensive database for Antarctic iceberg
tracking using scatterometer data," IEEE Journal of Selected Topics in Applied
Earth Observations, Vol. 11, No. 2,
doi:10.1109/JSTARS.2017.2784186, 2017.

The database provides mostly daily positions. ICE-NAV validates only +24-hour
displacement. +3h, +6h, and +12h outputs are model extrapolations and are not
independently validated at sub-daily resolution.

The source tracks giant tabular, scatterometer-resolvable icebergs, a different
size class from the 1–4 km-radius synthetic contacts. Accuracy demonstrates the
architecture for the observed giant-berg population, not validated small-berg
behaviour.

The processed 60–90°E, 80–60°S subset contains 95 icebergs and 45,345
observations from 1994-05-22 through 2004-06-30, with a median 24-hour interval.
Redistribution terms for the derived subset still require human confirmation;
the raw ZIP is therefore gitignored.

## ML experiment

Targets are local north/east displacement in kilometres. Features at T0 are
latitude, longitude, two recent velocity vectors, prior interval, horizon, and
day of year. Every feature timestamp is at or before T0. Group holdout keeps
iceberg IDs disjoint; temporal holdout trains only on earlier rows. The Random
Forest is deterministic (`random_state=26059`) and optional.

Free-drift historical accuracy is unavailable because no collocated historical
wind/current product is confirmed. Persistence and stationary baselines are
reported. The ML beats persistence on group-holdout mean error but not on the
temporal-holdout mean; it remains experimental.

## Forecast physics

Iceberg and sea-ice drift use `current + configured_wind_factor * wind`. Vector
directions are clockwise from true north and point toward motion. The 0.02
factors are first-order engineering assumptions and need a presentation-quality
scientific reference (`TODO(citation)`). Sea ice uses semi-Lagrangian backtrace
plus mild diffusion. Wind and current remain constant over 24 hours.

## Environmental sea-ice ingestion gate

No real environmental sea-ice product has been human-confirmed. Before binding
`fetch_seaice.py`, record exact product/version, DOI, licence, access method,
native projection/resolution, temporal coverage, latency, and format here. The
adapter supports EPSG:3031 transforms and missing-data semantics, but no real
scenario or source claim is fabricated.

A 25 km source displayed on the approximately 11 km grid does not gain real
detail. Missing pixels remain `data_quality: missing` and non-navigable.

## Validation boundary

Historical validation measures iceberg trajectory only. It does not validate
sea-ice advection, risk weights, routes, fuel index, or operational suitability.
