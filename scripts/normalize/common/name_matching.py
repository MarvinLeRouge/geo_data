from __future__ import annotations

MAX_DISTANCE = 2
AMBIGUITY_MARGIN = 1


class NameMatchError(ValueError):
    """Raised when a source name cannot be confidently matched to any candidate."""


class NameMatchAmbiguousError(NameMatchError):
    """Raised when two or more candidates are too close to the best match to pick
    one safely - refuses to guess rather than risk a wrong join."""


def levenshtein(a: str, b: str) -> int:
    """Computes the Levenshtein edit distance between two strings."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous_row = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current_row = [i] + [0] * len(b)
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current_row[j] = min(
                previous_row[j] + 1,
                current_row[j - 1] + 1,
                previous_row[j - 1] + cost,
            )
        previous_row = current_row
    return previous_row[-1]


def match_name(source_name: str, candidates: dict[str, str]) -> tuple[str, str]:
    """Matches `source_name` against `candidates`, exact first, then nearest by
    Levenshtein distance.

    Args:
        source_name (str): canonical name to match (e.g. INSEE's accented NCCENR).
        candidates (dict[str, str]): candidate key (e.g. geoBoundaries shapeID) ->
            candidate name (e.g. shapeName).

    Returns:
        tuple[str, str]: (matched candidate key, matched candidate name as found in
            the source - this is the "variant" a caller may want to record).

    Raises:
        NameMatchError: no candidate is within MAX_DISTANCE.
        NameMatchAmbiguousError: two or more candidates are within AMBIGUITY_MARGIN
            of each other at the top of the ranking.
    """
    normalized_source = source_name.strip()
    for key, name in candidates.items():
        if name.strip() == normalized_source:
            return key, name

    scored = sorted(
        (
            (levenshtein(normalized_source, name.strip()), key, name)
            for key, name in candidates.items()
        ),
        key=lambda item: item[0],
    )
    best_distance, best_key, best_name = scored[0]
    if best_distance > MAX_DISTANCE:
        raise NameMatchError(
            f"No candidate within distance {MAX_DISTANCE} for {source_name!r} "
            f"(closest: {best_name!r} at distance {best_distance})."
        )
    if len(scored) > 1 and scored[1][0] <= best_distance + AMBIGUITY_MARGIN:
        raise NameMatchAmbiguousError(
            f"Ambiguous match for {source_name!r}: {best_name!r} (distance "
            f"{best_distance}) vs {scored[1][2]!r} (distance {scored[1][0]})."
        )
    return best_key, best_name
