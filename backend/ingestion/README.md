# Offline ingestion

Runtime API handlers never download data. `iceberg_tracks.py --download` is a
manual, ahead-of-time utility for the confirmed BYU/NIC archive. Environmental
sea-ice fetching remains deliberately gated until the team records a specific
product, licence, DOI, projection, resolution, and access method in
`docs/methodology.md`.

From the repository root, while online once:

```bash
python -m backend.ingestion.iceberg_tracks --download
python -m backend.ingestion.train_iceberg_model
```

The first command caches the v8.0 ZIP and writes the tidy 60–90°E subset. Both
data files are ignored because explicit permission to republish a derived CSV
was not located on the source page. After acquisition, API and validation-page
requests use local files only and make no network calls.
