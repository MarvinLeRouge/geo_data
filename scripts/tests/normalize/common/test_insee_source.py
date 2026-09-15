from __future__ import annotations

from normalize.common.insee_source import load_metropolitan_departements, load_metropolitan_regions


def test_loads_exactly_13_metropolitan_regions():
    regions = load_metropolitan_regions()
    assert len(regions) == 13
    assert {"code": "84", "name": "Auvergne-Rhône-Alpes"} in regions
    assert all(r["code"] not in ("01", "02", "03", "04", "06") for r in regions)


def test_loads_exactly_96_metropolitan_departements():
    departements = load_metropolitan_departements()
    assert len(departements) == 96
    ain = next(d for d in departements if d["code"] == "01")
    assert ain == {"code": "01", "name": "Ain", "region_code": "84"}
    assert all(not d["code"].startswith(("97", "98")) for d in departements)
