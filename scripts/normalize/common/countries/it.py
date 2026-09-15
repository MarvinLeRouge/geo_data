from __future__ import annotations

from normalize.common.country_config import CountryConfig, LevelConfig

IT_CONFIG = CountryConfig(
    iso2="IT",
    iso3="ITA",
    levels={
        1: LevelConfig(handler="admin2_as_region", geoboundaries_adm=2),
        2: LevelConfig(handler="admin2_as_region", geoboundaries_adm=3),
    },
)
