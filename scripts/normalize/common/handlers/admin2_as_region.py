from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from shapely.geometry import shape as shapely_shape

from normalize.common.geoboundaries_source import load_geoboundaries_level
from normalize.common.handlers.base import ResolutionResult, ZoneRecord

if TYPE_CHECKING:
    from normalize.common.country_config import CountryConfig

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class UnresolvedParentError(ValueError):
    """Raised when one or more level-2 shapes' representative point falls outside
    every level-1 polygon, so no parent region can be assigned. Left unraised, this
    would surface later as an opaque rejection at GeoChallenge-Tracker's upload
    endpoint instead of here, where the operator can see which province failed."""


def _slugify(name: str) -> str:
    """Deterministic ASCII slug for a shape name, used as `feature_code` for
    countries with no local authoritative code table.

    Uses Unicode NFKD normalization plus combining-mark removal, so it handles
    any accented Latin letter (not just the small hardcoded set French/Italian
    text happens to use) - raises if the result is empty, since an empty
    feature_code silently becomes an unusable primary key downstream.
    """
    ascii_name = unicodedata.normalize("NFKD", name.lower())
    ascii_name = "".join(ch for ch in ascii_name if not unicodedata.combining(ch))
    slug = _SLUG_NON_ALNUM.sub("-", ascii_name).strip("-")
    if not slug:
        raise ValueError(f"_slugify produced an empty slug for {name!r}")
    return slug


def _slugify_checked(name: str, seen: dict[str, str]) -> str:
    """Slugifies `name` and raises if it collides with a different name already
    seen at this level - e.g. `Forli'-Cesena` and `Forlì-Cesena` both slugify to
    `forli-cesena`; letting the second overwrite the first in a lookup dict would
    silently drop a zone."""
    slug = _slugify(name)
    if slug in seen and seen[slug] != name:
        raise ValueError(f"Slug collision: {seen[slug]!r} and {name!r} both slugify to {slug!r}")
    seen[slug] = name
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
            records = []
            seen_slugs: dict[str, str] = {}
            for s in shapes.values():
                slug = _slugify_checked(s["name"], seen_slugs)
                records.append(ZoneRecord(feature_code=slug, name=s["name"], geometry=s["geometry"]))
            return ResolutionResult(records=records)

        parent_level_config = country_config.levels[1]
        parent_shapes = load_geoboundaries_level(
            country_config.iso3, parent_level_config.geoboundaries_adm
        )
        parent_seen_slugs: dict[str, str] = {}
        parent_geoms = {
            _slugify_checked(s["name"], parent_seen_slugs): shapely_shape(s["geometry"])
            for s in parent_shapes.values()
        }

        records = []
        unresolved = []
        seen_slugs = {}
        for s in shapes.values():
            slug = _slugify_checked(s["name"], seen_slugs)
            point = shapely_shape(s["geometry"]).representative_point()
            parent_code = next(
                (code for code, geom in parent_geoms.items() if geom.contains(point)),
                None,
            )
            if parent_code is None:
                unresolved.append(s["name"])
            records.append(
                ZoneRecord(
                    feature_code=slug,
                    name=s["name"],
                    geometry=s["geometry"],
                    parent_feature_code=parent_code,
                )
            )
        if unresolved:
            raise UnresolvedParentError(
                f"{len(unresolved)} shape(s) could not be assigned a parent region: {unresolved}"
            )
        return ResolutionResult(records=records)
