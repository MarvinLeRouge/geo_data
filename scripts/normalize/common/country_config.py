from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LevelConfig:
    """Per-level configuration: which handler resolves this level, and which
    geoBoundaries ADM level it reads geometry from."""

    handler: str
    geoboundaries_adm: int


@dataclass(frozen=True)
class CountryConfig:
    """One country's normalization configuration, consumed by pipeline.py."""

    iso2: str
    iso3: str
    levels: dict[int, LevelConfig]


from normalize.common.countries.fr import FR_CONFIG  # noqa: E402,F401
