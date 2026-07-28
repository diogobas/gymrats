"""Standard competition ranking.

Ties share the better position and the next distinct value skips: 1, 1, 3.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal

__all__ = ["competition_rank", "to_decimal"]


def to_decimal(value: float | Decimal) -> Decimal:
    """Compare values exactly.

    Every comparison in the tally goes through here. Binary floats would make
    ``0.1 + 0.2`` decide a championship, and the +20% calorie bonus multiplies
    exactly the kind of number that drifts.
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def competition_rank(
    pairs: Iterable[tuple[str, float | int | Decimal]],
    *,
    higher_is_better: bool = True,
) -> dict[str, int]:
    """Map each name to its position.

    ``higher_is_better`` is True for the leaderboards (more calories wins) and
    False for the season table (a lower point total wins).
    """
    ordered: Sequence[tuple[str, Decimal]] = sorted(
        ((name, to_decimal(value)) for name, value in pairs),
        key=lambda pair: pair[1],
        reverse=higher_is_better,
    )

    positions: dict[str, int] = {}
    previous_value: Decimal | None = None
    previous_position = 0

    for index, (name, value) in enumerate(ordered, start=1):
        if previous_value is not None and value == previous_value:
            position = previous_position
        else:
            position = index
        positions[name] = position
        previous_value, previous_position = value, position

    return positions
