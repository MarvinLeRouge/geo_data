from __future__ import annotations

import csv
from pathlib import Path

INSEE_DIR = Path(__file__).resolve().parents[3] / "data" / "insee"

# INSEE REG codes for the 5 overseas regions - out of scope for this migration
# (see Global Constraints in the implementation plan).
OVERSEAS_REGION_CODES = ("01", "02", "03", "04", "06")


def load_metropolitan_regions() -> list[dict[str, str]]:
    """Loads INSEE's metropolitan regions.

    Returns:
        list[dict[str, str]]: one dict per region, `{"code": "84", "name": "Auvergne-Rhône-Alpes"}`.
    """
    path = INSEE_DIR / "v_region_2026.csv"
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [
        {"code": row["REG"], "name": row["NCCENR"]}
        for row in rows
        if row["REG"] not in OVERSEAS_REGION_CODES
    ]


def load_metropolitan_departements() -> list[dict[str, str]]:
    """Loads INSEE's metropolitan departments.

    Returns:
        list[dict[str, str]]: one dict per department,
            `{"code": "01", "name": "Ain", "region_code": "84"}`.
    """
    path = INSEE_DIR / "v_departement_2026.csv"
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [
        {"code": row["DEP"], "name": row["NCCENR"], "region_code": row["REG"]}
        for row in rows
        if not row["DEP"].startswith(("97", "98"))
    ]
