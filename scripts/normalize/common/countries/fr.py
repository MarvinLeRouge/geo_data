from __future__ import annotations

from normalize.common.config_types import CountryConfig, LevelConfig

FR_CONFIG = CountryConfig(
    iso2="FR",
    iso3="FRA",
    levels={
        1: LevelConfig(handler="insee_geoboundaries_join", geoboundaries_adm=1),
        2: LevelConfig(handler="insee_geoboundaries_join", geoboundaries_adm=2),
    },
)
