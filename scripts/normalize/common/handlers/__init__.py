from __future__ import annotations

from normalize.common.handlers.admin2_as_region import Admin2AsRegionHandler
from normalize.common.handlers.base import NormalizationHandler
from normalize.common.handlers.insee_geoboundaries_join import InseeGeoboundariesJoinHandler

HANDLERS: dict[str, NormalizationHandler] = {
    "insee_geoboundaries_join": InseeGeoboundariesJoinHandler(),
    "admin2_as_region": Admin2AsRegionHandler(),
}
