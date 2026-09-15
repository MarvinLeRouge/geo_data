from __future__ import annotations

from unittest.mock import patch

import pytest

from normalize.common.country_config import CountryConfig, LevelConfig
from normalize.common.handlers.base import ResolutionResult
from normalize.common.handlers.insee_geoboundaries_join import InseeGeoboundariesJoinHandler
from normalize.common.name_matching import NameMatchError

FR_CONFIG = CountryConfig(
    iso2="FR",
    iso3="FRA",
    levels={
        1: LevelConfig(handler="insee_geoboundaries_join", geoboundaries_adm=1),
        2: LevelConfig(handler="insee_geoboundaries_join", geoboundaries_adm=2),
    },
)


def _shape(name: str) -> dict:
    return {"name": name, "iso": "", "geometry": {"type": "Point", "coordinates": [0, 0]}}


HANDLER_MODULE = "normalize.common.handlers.insee_geoboundaries_join"


class TestResolveRegions:
    def test_resolves_exact_name_matches(self):
        shapes = {"shape-84": _shape("Auvergne-Rhône-Alpes")}
        regions = [{"code": "84", "name": "Auvergne-Rhône-Alpes"}]
        with (
            patch(f"{HANDLER_MODULE}.load_geoboundaries_level", return_value=shapes),
            patch(f"{HANDLER_MODULE}.load_metropolitan_regions", return_value=regions),
        ):
            result = InseeGeoboundariesJoinHandler().resolve(1, FR_CONFIG)

        assert isinstance(result, ResolutionResult)
        assert len(result.records) == 1
        record = result.records[0]
        assert record.feature_code == "84"
        assert record.name == "Auvergne-Rhône-Alpes"
        assert record.parent_feature_code is None
        assert result.name_variants == {}

    def test_records_a_name_variant_when_geoboundaries_spelling_differs(self):
        shapes = {"shape-11": _shape("Ile-de-France")}
        regions = [{"code": "11", "name": "Île-de-France"}]
        with (
            patch(f"{HANDLER_MODULE}.load_geoboundaries_level", return_value=shapes),
            patch(f"{HANDLER_MODULE}.load_metropolitan_regions", return_value=regions),
        ):
            result = InseeGeoboundariesJoinHandler().resolve(1, FR_CONFIG)

        assert result.records[0].name == "Île-de-France"  # INSEE spelling stays canonical
        assert result.name_variants == {"11": "Ile-de-France"}


class TestResolveDepartements:
    def test_resolves_and_attaches_parent_region_code(self):
        shapes = {"shape-01": _shape("Ain")}
        departements = [{"code": "01", "name": "Ain", "region_code": "84"}]
        with (
            patch(f"{HANDLER_MODULE}.load_geoboundaries_level", return_value=shapes),
            patch(f"{HANDLER_MODULE}.load_metropolitan_departements", return_value=departements),
        ):
            result = InseeGeoboundariesJoinHandler().resolve(2, FR_CONFIG)

        record = result.records[0]
        assert record.feature_code == "01"
        assert record.parent_feature_code == "84"

    def test_matches_the_real_cotes_darmor_hyphen_variant(self):
        shapes = {"shape-22": _shape("Côtes d'Armor")}
        departements = [{"code": "22", "name": "Côtes-d'Armor", "region_code": "53"}]
        with (
            patch(f"{HANDLER_MODULE}.load_geoboundaries_level", return_value=shapes),
            patch(f"{HANDLER_MODULE}.load_metropolitan_departements", return_value=departements),
        ):
            result = InseeGeoboundariesJoinHandler().resolve(2, FR_CONFIG)

        assert result.records[0].name == "Côtes-d'Armor"
        assert result.name_variants == {"22": "Côtes d'Armor"}

    def test_raises_when_join_fails(self):
        shapes = {"shape-99": _shape("Not A Real Department")}
        departements = [{"code": "01", "name": "Ain", "region_code": "84"}]
        with (
            patch(f"{HANDLER_MODULE}.load_geoboundaries_level", return_value=shapes),
            patch(f"{HANDLER_MODULE}.load_metropolitan_departements", return_value=departements),
        ):
            with pytest.raises(NameMatchError):
                InseeGeoboundariesJoinHandler().resolve(2, FR_CONFIG)


def test_raises_for_unsupported_level():
    with patch(f"{HANDLER_MODULE}.load_geoboundaries_level", return_value={}):
        with pytest.raises(ValueError, match="does not support level"):
            InseeGeoboundariesJoinHandler().resolve(0, FR_CONFIG)
