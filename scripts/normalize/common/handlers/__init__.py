from __future__ import annotations

from normalize.common.handlers.base import NormalizationHandler
from normalize.common.handlers.insee_geoboundaries_join import InseeGeoboundariesJoinHandler

HANDLERS: dict[str, NormalizationHandler] = {
    "insee_geoboundaries_join": InseeGeoboundariesJoinHandler(),
}
