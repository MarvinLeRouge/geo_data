# Scripts

## Download

- `download_geoboundaries.py` - fetches geoBoundaries ADM0-5 archives per country into `data/geoboundaries/{ISO3}/`.
- `download_geonames.py` - fetches geonames admin code tables into `data/geonames/`.

## Normalize

`normalize/` turns the raw sources above into CONTRACT.md-compliant zone files:

- `normalize/common/` - generic, project-agnostic join framework (handlers, country configs, pipeline orchestration). Output: `data/normalized/{cc}/adm{level}.geojson` (generic schema: `feature_code`, `name`, `parent_feature_code`).
- `normalize/gctracker/export_contract.py` - GeoChallenge-Tracker-specific shaping step: computes `bbox`, prefixes codes, renames properties to match `docs/CONTRACT.md`.

Run a country's full pipeline:

```bash
uv run python -m normalize.common.pipeline FR
uv run python -m normalize.gctracker.export_contract FR
```

## Docs

- `docs/CONTRACT.md` - the normalized output schema, agreed with GeoChallenge-Tracker.
- `docs/SOURCES.md` - per-country/per-level attribution tracking.
