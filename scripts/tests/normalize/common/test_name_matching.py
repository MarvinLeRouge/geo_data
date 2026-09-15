from __future__ import annotations

import pytest

from normalize.common.name_matching import NameMatchAmbiguousError, NameMatchError, match_name


def test_exact_match_returns_directly():
    candidates = {"shape-1": "Ain", "shape-2": "Aisne"}
    assert match_name("Ain", candidates) == ("shape-1", "Ain")


def test_matches_the_real_cotes_darmor_hyphen_vs_space_variant():
    # Real case: geoBoundaries FRA ADM2 has "Côtes d'Armor", INSEE has "Côtes-d'Armor".
    candidates = {"shape-1": "Côtes d'Armor", "shape-2": "Côte-d'Or"}
    assert match_name("Côtes-d'Armor", candidates) == ("shape-1", "Côtes d'Armor")


def test_strips_surrounding_whitespace_before_matching():
    # Real case: geoBoundaries FRA ADM2 has a trailing non-breaking space on "Indre-et-Loire".
    candidates = {"shape-1": "Indre-et-Loire\xa0"}
    assert match_name("Indre-et-Loire", candidates) == ("shape-1", "Indre-et-Loire\xa0")


def test_raises_when_no_candidate_within_threshold():
    candidates = {"shape-1": "Completely Different Name"}
    with pytest.raises(NameMatchError):
        match_name("Ain", candidates)


def test_raises_when_two_candidates_are_ambiguously_close():
    # Both "Aube" and "Aule" are 1 edit away from "Aude" - must not guess.
    candidates = {"shape-1": "Aube", "shape-2": "Aule"}
    with pytest.raises(NameMatchAmbiguousError):
        match_name("Aude", candidates)
