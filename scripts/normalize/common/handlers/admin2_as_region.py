from __future__ import annotations

import re
from typing import TYPE_CHECKING

from shapely.geometry import shape as shapely_shape

from normalize.common.geoboundaries_source import load_geoboundaries_level
from normalize.common.handlers.base import ResolutionResult, ZoneRecord

if TYPE_CHECKING:
    from normalize.common.country_config import CountryConfig

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    ascii_name = (
        name.lower()
        .replace("à", "a")
        .replace("â", "a")
        .replace("è", "e")
        .replace("é", "e")
        .replace("ì", "i")
        .replace("ò", "o")
        .replace("ù", "u")
    )
    slug = _SLUG_NON_ALNUM.sub("-", ascii_name).strip("-")
    return slug


class Admin2AsRegionHandler:
    """Uses a geoBoundaries ADM level one step finer than usual as the output level,
    for countries whose "natural" ADM1 is too coarse (e.g. Italy's ADM1 is 5 macro-areas,
    not its 20 administrative regions - see the implementation plan's Task 12 rationale).

    There is no local authoritative code table to join against for these countries, so
    `feature_code` is a deterministic slug of the geoBoundaries `shapeName`, and (level 2
    only) `parent_feature_code` is resolved by point-in-polygon containment (using each
    shape's `representative_point()`, not its `centroid` - see below) against the
    level 1 shapes, since geoBoundaries carries no attribute linking the two levels.
    """

    def resolve(self, level: int, country_config: "CountryConfig") -> ResolutionResult:
        if level not in (1, 2):
            raise ValueError(f"admin2_as_region does not support level {level}")

        level_config = country_config.levels[level]
        shapes = load_geoboundaries_level(country_config.iso3, level_config.geoboundaries_adm)

        if level == 1:
            records = [
                ZoneRecord(feature_code=_slugify(s["name"]), name=s["name"], geometry=s["geometry"])
                for s in shapes.values()
            ]
            return ResolutionResult(records=records)

        parent_level_config = country_config.levels[1]
        parent_shapes = load_geoboundaries_level(
            country_config.iso3, parent_level_config.geoboundaries_adm
        )
        parent_geoms = {
            _slugify(s["name"]): shapely_shape(s["geometry"]) for s in parent_shapes.values()
        }

        records = []
        for s in shapes.values():
            point = shapely_shape(s["geometry"]).representative_point()
            parent_code = next(
                (code for code, geom in parent_geoms.items() if geom.contains(point)),
                None,
            )
            records.append(
                ZoneRecord(
                    feature_code=_slugify(s["name"]),
                    name=s["name"],
                    geometry=s["geometry"],
                    parent_feature_code=parent_code,
                )
            )
        return ResolutionResult(records=records)
