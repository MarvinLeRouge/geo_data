from __future__ import annotations

import json
from pathlib import Path

from normalize.common.country_config import FR_CONFIG
from normalize.common.pipeline import run_pipeline


def test_fr_pipeline_produces_109_metropolitan_zones(tmp_path: Path):
    run_pipeline(FR_CONFIG, tmp_path)

    adm1 = json.loads((tmp_path / "FR" / "adm1.geojson").read_text())
    adm2 = json.loads((tmp_path / "FR" / "adm2.geojson").read_text())

    assert adm1["type"] == "FeatureCollection"
    assert len(adm1["features"]) == 13
    assert len(adm2["features"]) == 96

    idf = next(f for f in adm1["features"] if f["properties"]["feature_code"] == "11")
    assert idf["properties"]["name"] == "Île-de-France"
    assert "parent_feature_code" not in idf["properties"] or idf["properties"]["parent_feature_code"] is None

    ain = next(f for f in adm2["features"] if f["properties"]["feature_code"] == "01")
    assert ain["properties"]["parent_feature_code"] == "84"


def test_fr_pipeline_writes_name_variants_file(tmp_path: Path):
    run_pipeline(FR_CONFIG, tmp_path)

    variants = json.loads((tmp_path / "FR" / "name_variants.json").read_text())
    # Real, known variants for the current data snapshot.
    assert variants["22"] == "Côtes d'Armor"
