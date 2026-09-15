from __future__ import annotations

from typing import TYPE_CHECKING

from normalize.common.geoboundaries_source import load_geoboundaries_level
from normalize.common.handlers.base import ResolutionResult, ZoneRecord
from normalize.common.insee_source import load_metropolitan_departements, load_metropolitan_regions
from normalize.common.name_matching import match_name

if TYPE_CHECKING:
    from normalize.common.country_config import CountryConfig


class InseeGeoboundariesJoinHandler:
    """Joins INSEE's authoritative codes/names to geoBoundaries geometry, by name.

    Used for France: preserves the exact region/department codes already live in
    GeoChallenge-Tracker's database, which a direct geoBoundaries `shapeISO`
    mapping would not. INSEE's accented name is the canonical reference; any
    geoBoundaries spelling variant is recorded, not silently discarded.
    """

    def resolve(self, level: int, country_config: "CountryConfig") -> ResolutionResult:
        if level not in (1, 2):
            raise ValueError(f"insee_geoboundaries_join does not support level {level}")

        level_config = country_config.levels[level]
        shapes = load_geoboundaries_level(country_config.iso3, level_config.geoboundaries_adm)
        candidates = {shape_id: shape["name"] for shape_id, shape in shapes.items()}

        if level == 1:
            return self._resolve_regions(candidates, shapes)
        return self._resolve_departements(candidates, shapes)

    def _resolve_regions(self, candidates: dict[str, str], shapes: dict) -> ResolutionResult:
        records = []
        variants = {}
        for region in load_metropolitan_regions():
            shape_id, matched_name = match_name(region["name"], candidates)
            if matched_name != region["name"]:
                variants[region["code"]] = matched_name
            records.append(
                ZoneRecord(
                    feature_code=region["code"],
                    name=region["name"],
                    geometry=shapes[shape_id]["geometry"],
                )
            )
        return ResolutionResult(records=records, name_variants=variants)

    def _resolve_departements(self, candidates: dict[str, str], shapes: dict) -> ResolutionResult:
        records = []
        variants = {}
        for departement in load_metropolitan_departements():
            shape_id, matched_name = match_name(departement["name"], candidates)
            if matched_name != departement["name"]:
                variants[departement["code"]] = matched_name
            records.append(
                ZoneRecord(
                    feature_code=departement["code"],
                    name=departement["name"],
                    geometry=shapes[shape_id]["geometry"],
                    parent_feature_code=departement["region_code"],
                )
            )
        return ResolutionResult(records=records, name_variants=variants)
