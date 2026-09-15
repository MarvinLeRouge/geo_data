from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import shape


def _export_feature(country_code: str, feature: dict) -> dict:
    props = feature["properties"]
    code = f"{country_code}-{props['feature_code']}"
    exported_props = {"code": code, "nom": props["name"], "feature_code": props["feature_code"]}
    if props.get("parent_feature_code") is not None:
        exported_props["parent_code"] = f"{country_code}-{props['parent_feature_code']}"

    bbox = list(shape(feature["geometry"]).bounds)
    return {
        "type": "Feature",
        "properties": exported_props,
        "geometry": feature["geometry"],
        "bbox": bbox,
    }


def export_country(country_code: str, normalized_dir: Path, output_dir: Path) -> None:
    """Shapes a country's generic normalized files into CONTRACT.md's exact schema.

    Args:
        country_code (str): ISO 3166-1 alpha-2 code, e.g. "FR".
        normalized_dir (Path): base directory containing `{country_code}/adm{level}.geojson`
            generic files (as written by `pipeline.run_pipeline`).
        output_dir (Path): base directory to write CONTRACT.md-shaped files to,
            same `{country_code}/adm{level}.geojson` layout.
    """
    source_dir = normalized_dir / country_code
    dest_dir = output_dir / country_code
    dest_dir.mkdir(parents=True, exist_ok=True)

    for source_path in sorted(source_dir.glob("adm[12].geojson")):
        payload = json.loads(source_path.read_text())
        exported = {
            "type": "FeatureCollection",
            "features": [_export_feature(country_code, f) for f in payload["features"]],
        }
        (dest_dir / source_path.name).write_text(json.dumps(exported, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m normalize.gctracker.export_contract <COUNTRY_CODE>")
        sys.exit(1)

    export_country(sys.argv[1], Path("data/normalized"), Path("data/gctracker_export"))
