from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from normalize.common.country_config import CountryConfig


@dataclass(frozen=True)
class ZoneRecord:
    """A single resolved administrative zone, before country-specific export shaping."""

    feature_code: str
    name: str
    geometry: dict[str, Any]
    parent_feature_code: str | None = None


@dataclass(frozen=True)
class ResolutionResult:
    """A handler's output for one country/level.

    `name_variants` maps a zone's `feature_code` to the source spelling that was
    matched (e.g. a geoBoundaries `shapeName`) whenever it differs from the
    canonical reference name - recorded rather than silently discarded.
    """

    records: list[ZoneRecord]
    name_variants: dict[str, str] = field(default_factory=dict)


class NormalizationHandler(Protocol):
    """Common interface implemented by each join strategy."""

    def resolve(self, level: int, country_config: "CountryConfig") -> ResolutionResult: ...
