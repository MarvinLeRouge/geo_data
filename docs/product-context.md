[🇫🇷 Version française](product-context.fr.md) | 🇬🇧 English version

---

# Product Context - geo_data

## Concept

Projects that work with territories (countries, regions, departments) all need the same administrative boundaries, and public sources publish them in different shapes, codes and languages. geo_data is a cross-project tool that centralizes these geographic sources and normalizes them once into a single generic schema. Each consuming project, public or private, then gets its data through a small export step shaped to its own format, instead of maintaining its own download and cleanup scripts. GeoChallenge-Tracker, which tracks geocaching challenges by administrative zone, is one such consumer.

## Target user

A developer who needs clean administrative zones in a project, running the pipeline locally when a country is added or a source changes. No end users, no hosted service.

## Core vocabulary

| Term | Meaning |
|---|---|
| `ADM level` | Administrative depth: 0 country, 1 region-equivalent, 2 department-equivalent |
| `feature_code` | Raw admin unit code from the source, without country prefix (e.g. `84`) |
| `normalized output` | Generic, project-agnostic files `data/normalized/{cc}/adm{level}.geojson` (`feature_code`, `name`, `parent_feature_code`) |
| `export` | Consumer-specific step that reshapes the normalized output into one project's format |
| `contract` | The output schema agreed with a consumer, e.g. GeoChallenge-Tracker's `scripts/docs/CONTRACT.md` |
| `country config` | Per-country description of which source and handler feed each level (`normalize/common/countries/`) |

## Features

- **Download** - geoBoundaries ADM0-5 archives per country, GeoNames admin code tables
- **Normalize** - a generic join framework (sources, handlers, name matching) builds the normalized output; France joins the INSEE code files kept in `data/insee/`, Italy promotes its admin2 units to regions
- **Export** - one step per consumer; the GeoChallenge-Tracker export adds `bbox`, prefixes codes (`FR-84`) and renames properties to match its contract
- **Attribution** - per-country, per-level source tracking in `SOURCES.md` and `CREDITS.md`

## Non-goals

- No API, no UI, no scheduled run: a local CLI pipeline
- No direct write to a consumer's database: export files are the only interface
- No contract change without agreement with the consumer concerned
