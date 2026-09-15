from __future__ import annotations

import json
from pathlib import Path

from normalize.common.country_config import CountryConfig
from normalize.common.handlers import HANDLERS
from normalize.common.handlers.base import ZoneRecord


def _feature(record: ZoneRecord) -> dict:
    properties = {"feature_code": record.feature_code, "name": record.name}
    if record.parent_feature_code is not None:
        properties["parent_feature_code"] = record.parent_feature_code
    return {"type": "Feature", "properties": properties, "geometry": record.geometry}


def run_pipeline(country_config: CountryConfig, output_dir: Path) -> None:
    """Runs every configured level's handler for a country and writes generic
    normalized GeoJSON files plus a name-variants report.

    Args:
        country_config (CountryConfig): which handler/geoBoundaries ADM level to
            use per output level.
        output_dir (Path): base directory; output goes to
            `{output_dir}/{iso2}/adm{level}.geojson`.
    """
    country_dir = output_dir / country_config.iso2
    country_dir.mkdir(parents=True, exist_ok=True)

    all_variants: dict[str, dict[str, str]] = {}
    for level in sorted(country_config.levels):
        handler = HANDLERS[country_config.levels[level].handler]
        result = handler.resolve(level, country_config)
        if result.name_variants:
            all_variants[str(level)] = result.name_variants

        feature_collection = {
            "type": "FeatureCollection",
            "features": [_feature(record) for record in result.records],
        }
        (country_dir / f"adm{level}.geojson").write_text(
            json.dumps(feature_collection, ensure_ascii=False, indent=2)
        )

    if all_variants:
        (country_dir / "name_variants.json").write_text(
            json.dumps(all_variants, ensure_ascii=False, indent=2, sort_keys=True)
        )


def _load_country_config(country_code: str) -> CountryConfig:
    """Looks up a country's config by convention: `{code}_CONFIG` in `country_config`.

    This makes `python -m normalize.common.pipeline <CODE>` work for any country
    whose config is re-exported from `country_config.py`, without needing to edit
    this module every time a new country is added (e.g. Task 13 adding IT_CONFIG).
    """
    import normalize.common.country_config as country_config_module

    try:
        return getattr(country_config_module, f"{country_code}_CONFIG")
    except AttributeError as exc:
        raise ValueError(f"No CountryConfig registered for {country_code!r}") from exc


if __name__ == "__main__":
    import sys

    run_pipeline(_load_country_config(sys.argv[1]), Path("data/normalized"))
