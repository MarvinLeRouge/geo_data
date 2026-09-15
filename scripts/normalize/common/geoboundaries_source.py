from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

GEOBOUNDARIES_DIR = Path(__file__).resolve().parents[3] / "data" / "geoboundaries"


def load_geoboundaries_level(iso3: str, adm_level: int) -> dict[str, dict[str, Any]]:
    """Loads one country's geoBoundaries ADM level, keyed by shapeID.

    Args:
        iso3 (str): geoBoundaries ISO3 country code (e.g. "FRA").
        adm_level (int): geoBoundaries ADM level to load (0-5).

    Returns:
        dict[str, dict[str, Any]]: shapeID -> {"name": str, "iso": str, "geometry": dict}.

    Raises:
        FileNotFoundError: if the archive for this country/level is not on disk.
    """
    archive_path = GEOBOUNDARIES_DIR / iso3 / f"geoBoundaries-{iso3}-ADM{adm_level}-all.zip"
    if not archive_path.exists():
        raise FileNotFoundError(f"No geoBoundaries archive at {archive_path}")

    member_name = f"geoBoundaries-{iso3}-ADM{adm_level}.geojson"
    with zipfile.ZipFile(archive_path) as archive, archive.open(member_name) as member:
        payload = json.load(member)

    shapes: dict[str, dict[str, Any]] = {}
    for feature in payload["features"]:
        props = feature["properties"]
        shapes[props["shapeID"]] = {
            "name": props["shapeName"].strip(),
            "iso": props["shapeISO"],
            "geometry": feature["geometry"],
        }
    return shapes
