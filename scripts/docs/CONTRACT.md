# Normalized data contract (geo_json -> GeoChallenge-Tracker)

This document defines the exact output format this project must produce so
that GeoChallenge-Tracker's admin upload endpoint can consume it. Any change
to this contract must be agreed on both sides (this project and
GeoChallenge-Tracker) before implementation.

## Storage layout

- `raw/{country_code}/...` — untouched data as downloaded from geoBoundaries,
  kept for traceability and reprocessing. Internal structure is free (whatever
  geoBoundaries' API/download returns).
- `normalized/{country_code}/adm{level}.geojson` — normalized output, one file
  per administrative level, where `{level}` is `0`, `1`, or `2`:
  - `adm0.geojson` — country boundary
  - `adm1.geojson` — region-equivalent subdivisions
  - `adm2.geojson` — department-equivalent subdivisions
- `{country_code}` is the ISO 3166-1 alpha-2 code, uppercase (e.g. `FR`).

## Normalized GeoJSON feature schema

Each `adm{level}.geojson` file is a standard GeoJSON `FeatureCollection`.
Each `Feature.properties` object must contain:

| Property       | Type   | Levels | Description |
|----------------|--------|--------|-------------|
| `code`         | string | 0,1,2  | Stable zone code. Level 0: `{country_code}` (e.g. `FR`). Levels 1/2: `{country_code}-{feature_code}` (e.g. `FR-84`), matching the existing France convention. |
| `nom`          | string | 0,1,2  | Display name. Named `nom` (not `name`) for compatibility with existing GeoChallenge-Tracker frontend code that reads `feature.properties.nom`. |
| `feature_code` | string | 0,1,2  | Raw admin unit code without country prefix (e.g. `84`). |
| `parent_code`  | string | 2 only | Code of the parent level-1 zone (e.g. `FR-11`). Absent/null at levels 0 and 1. |

Each `Feature` must also carry a standard GeoJSON `bbox` member
(`[lon_min, lat_min, lon_max, lat_max]`), computed from its geometry.

This mirrors GeoChallenge-Tracker's `AdministrativeZone` MongoDB model
(`code`, `country_code`, `level`, `name`, `parent_code`, `geojson_file`,
`feature_code`, `bbox`), which the future GCTracker upload endpoint will
populate from these files.

## Attribution

geoBoundaries data is CC-BY 4.0. A `SOURCES.md` at the project root must
track, per country and per level: source name, license, source URL, and the
date the data was fetched.

## Out of scope for this contract

- ADM0 (level 0) has no current consumer in GeoChallenge-Tracker (the World
  view is list-based, not map-based, as of this writing). It is still part
  of the contract for forward-compatibility, but is not urgent.
- The actual download/normalization implementation (language, libraries,
  geoBoundaries API details) is not covered here - this document only fixes
  the output contract.
