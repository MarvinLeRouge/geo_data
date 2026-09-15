from __future__ import annotations

import pytest

from normalize.common.geoboundaries_source import load_geoboundaries_level


def test_loads_fra_adm1_with_13_shapes():
    shapes = load_geoboundaries_level("FRA", 1)
    assert len(shapes) == 13
    names = {shape["name"] for shape in shapes.values()}
    assert "Île-de-France" in names


def test_raises_file_not_found_for_unknown_country():
    with pytest.raises(FileNotFoundError):
        load_geoboundaries_level("ZZZ", 1)
