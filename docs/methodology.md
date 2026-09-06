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
The archive is publicly downloadable, but the source page does not state an
explicit redistribution licence for republishing a derived CSV. The raw ZIP and
processed track subset are therefore gitignored; each demo machine must run the
documented ahead-of-time acquisition step while online, then operates offline.

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
CONFIRMED source: NOAA/NSIDC Climate Data Record of Passive Microwave Sea Ice
Concentration, Version 6 (dataset G02202). DOI 10.7265/b18j-z797. Citation:
Meier, W. N., Fetterer, F., Windnagel, A. K., Stewart, J. S. & Stafford, T.
(2024). NetCDF, EPSG:3412 (NSIDC Sea Ice Polar Stereographic South), 25 km
grid, daily files, 1978-present. Verified directly against a live granule
(sic_pss25_20230715_F17_v06r00.nc) in this environment: no Earthdata Login
is required for this specific mirror (noaadata.apps.nsidc.org), contrary to
NSIDC's general guidance for other access paths; concentration is decoded by
netCDF4 into [0,1] with missing/land/pole-hole pixels as MaskedArray entries,
never as out-of-range sentinels. As with the BYU/NIC iceberg archive, no
explicit redistribution licence for a derived subset was located, so raw
granules and built real_scenario_*.json files are gitignored; each machine
runs the acquisition step once.

For 2023-07-15 (mid-winter, near seasonal maximum): 739 of 900 corridor cells
returned an observed concentration (0.62-1.00), 161 were missing. Icebergs
are intentionally omitted from observed scenarios -- there is no real-time
position feed; the BYU/NIC archive is historical only.

One-time acquisition:

    python -m backend.ingestion.fetch_seaice --download --date 2023-07-15
    python -m backend.data.build_real_scenario --date 2023-07-15

## Validation boundary

Historical validation measures iceberg trajectory only. It does not validate
sea-ice advection, risk weights, routes, fuel index, or operational suitability.
