from __future__ import annotations

from unittest.mock import patch

from normalize.common.country_config import CountryConfig, LevelConfig
from normalize.common.handlers.admin2_as_region import Admin2AsRegionHandler

HANDLER_MODULE = "normalize.common.handlers.admin2_as_region"

IT_CONFIG = CountryConfig(
    iso2="IT",
    iso3="ITA",
    levels={
        1: LevelConfig(handler="admin2_as_region", geoboundaries_adm=2),
        2: LevelConfig(handler="admin2_as_region", geoboundaries_adm=3),
    },
)


def _shape(name: str, coordinates: list) -> dict:
    return {
        "name": name,
        "iso": "",
        "geometry": {"type": "Polygon", "coordinates": [coordinates]},
    }


# A 2x2 square used as the "region" for level 1 and as the containing shape for level 2.
REGION_SQUARE = [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]
# A small square fully inside REGION_SQUARE, used as the "province" for level 2.
PROVINCE_SQUARE = [[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0], [0.5, 0.5]]


class TestResolveLevel1:
    def test_slugifies_shape_name_into_feature_code(self):
        shapes = {"shape-1": _shape("Valle d'Aosta", REGION_SQUARE)}
        with patch(f"{HANDLER_MODULE}.load_geoboundaries_level", return_value=shapes):
            result = Admin2AsRegionHandler().resolve(1, IT_CONFIG)

        assert len(result.records) == 1
        record = result.records[0]
        assert record.feature_code == "valle-d-aosta"
        assert record.name == "Valle d'Aosta"
        assert record.parent_feature_code is None


class TestResolveLevel2:
    def test_resolves_parent_by_geometric_containment(self):
        def _load(iso3: str, adm_level: int):
            if adm_level == 2:
                return {"region-1": _shape("Piemonte", REGION_SQUARE)}
            return {"province-1": _shape("Torino", PROVINCE_SQUARE)}

        with patch(f"{HANDLER_MODULE}.load_geoboundaries_level", side_effect=_load):
            result = Admin2AsRegionHandler().resolve(2, IT_CONFIG)

        assert len(result.records) == 1
        record = result.records[0]
        assert record.feature_code == "torino"
        assert record.parent_feature_code == "piemonte"

    def test_resolves_parent_for_a_province_with_a_distant_offshore_part(self):
        # Regression test for a real failure found against the actual Italy data:
        # a province whose geometry has two disjoint, similarly-sized parts (like
        # Livorno's mainland territory plus Elba and other islands) has an
        # area-weighted centroid that can land in the gap between them, outside
        # every region - representative_point() must be used instead, since it is
        # guaranteed to fall inside the geometry.
        region_square = [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0], [0.0, 0.0]]
        island_shape = {
            "name": "Livorno",
            "iso": "",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [[[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0], [0.5, 0.5]]],
                    [[[20.0, 20.0], [20.5, 20.0], [20.5, 20.5], [20.0, 20.5], [20.0, 20.0]]],
                ],
            },
        }

        def _load(iso3: str, adm_level: int):
            if adm_level == 2:
                return {"region-1": _shape("Toscana", region_square)}
            return {"province-1": island_shape}

        with patch(f"{HANDLER_MODULE}.load_geoboundaries_level", side_effect=_load):
            result = Admin2AsRegionHandler().resolve(2, IT_CONFIG)

        assert result.records[0].parent_feature_code == "toscana"
