from __future__ import annotations

from normalize.common.handlers.base import ResolutionResult, ZoneRecord


def test_zone_record_holds_its_fields():
    record = ZoneRecord(
        feature_code="84",
        name="Auvergne-Rhône-Alpes",
        geometry={"type": "Point", "coordinates": [0, 0]},
    )
    assert record.feature_code == "84"
    assert record.parent_feature_code is None


def test_resolution_result_defaults_to_no_variants():
    result = ResolutionResult(records=[])
    assert result.records == []
    assert result.name_variants == {}
