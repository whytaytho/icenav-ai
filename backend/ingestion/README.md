# Offline ingestion

Runtime API handlers never download data. `iceberg_tracks.py --download` is a
manual, ahead-of-time utility for the confirmed BYU/NIC archive. Environmental
sea-ice fetching remains deliberately gated until the team records a specific
product, licence, DOI, projection, resolution, and access method in
`docs/methodology.md`.
