from __future__ import annotations

import json
from pathlib import Path

from normalize.gctracker.export_contract import export_country


def _write_generic_fc(path: Path, features: list[dict]) -> None:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def test_exports_level_1_with_prefixed_code_and_bbox(tmp_path: Path):
    normalized_dir = tmp_path / "normalized"
    (normalized_dir / "FR").mkdir(parents=True)
    _write_generic_fc(
        normalized_dir / "FR" / "adm1.geojson",
        [
            {
                "type": "Feature",
                "properties": {"feature_code": "84", "name": "Auvergne-Rhône-Alpes"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[4.0, 44.0], [7.0, 44.0], [7.0, 46.5], [4.0, 46.5], [4.0, 44.0]]],
                },
            }
        ],
    )
    output_dir = tmp_path / "output"

    export_country("FR", normalized_dir, output_dir)

    exported = json.loads((output_dir / "FR" / "adm1.geojson").read_text())
    feature = exported["features"][0]
    assert feature["properties"] == {"code": "FR-84", "nom": "Auvergne-Rhône-Alpes", "feature_code": "84"}
    assert feature["bbox"] == [4.0, 44.0, 7.0, 46.5]


def test_exports_level_2_with_prefixed_parent_code(tmp_path: Path):
    normalized_dir = tmp_path / "normalized"
    (normalized_dir / "FR").mkdir(parents=True)
    _write_generic_fc(
        normalized_dir / "FR" / "adm2.geojson",
        [
            {
                "type": "Feature",
                "properties": {"feature_code": "01", "name": "Ain", "parent_feature_code": "84"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[5.0, 45.0], [6.0, 45.0], [6.0, 46.0], [5.0, 46.0], [5.0, 45.0]]],
                },
            }
        ],
    )
    output_dir = tmp_path / "output"

    export_country("FR", normalized_dir, output_dir)

    exported = json.loads((output_dir / "FR" / "adm2.geojson").read_text())
    feature = exported["features"][0]
    assert feature["properties"]["code"] == "FR-01"
    assert feature["properties"]["parent_code"] == "FR-84"
