"""The tiebreak cascade.

Applied whenever two or more people share a score:

  a) more distance in the period
  b) more duration in the period
  c) still level -> do not pick a winner. The tie is reported as unresolved
     and a human decides.

The same cascade serves the month (using "Este mês" numbers) and the season
(using "Este ano" numbers) -- only the period changes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from .models import TIEBREAK_MODALITIES, Modality, Period, Tables, TiebreakInfo
from .ranking import to_decimal

__all__ = ["TiebreakOutcome", "break_tie", "order_with_tiebreaks"]


@dataclass(frozen=True)
class TiebreakOutcome:
    """The result of running the cascade over one tied group.

    ``blocks`` is the group split and ordered. A block with more than one name
    survived the whole cascade and is an unresolved tie.
    """

    blocks: tuple[tuple[str, ...], ...]
    resolved_by: Mapping[str, Modality | None]
    comparison: Mapping[str, Mapping[str, float]]

    @property
    def unresolved(self) -> tuple[tuple[str, ...], ...]:
        return tuple(block for block in self.blocks if len(block) > 1)


def _value(tables: Tables, name: str, modality: Modality, period: Period) -> Decimal:
    """Missing means the person is not on that leaderboard at all.

    Treated as the worst possible value rather than as zero-and-equal, so an
    absent row never ties with a real one.
    """
    raw = tables.value_for(name, modality, period)
    if raw is None:
        return Decimal("-Infinity")
    return to_decimal(raw)


def break_tie(
    names: Sequence[str],
    tables: Tables,
    period: Period,
    criteria: Sequence[Modality] | None = None,
) -> TiebreakOutcome:
    """Split ``names`` into ordered blocks using the cascade."""
    if criteria is None:
        criteria = TIEBREAK_MODALITIES

    resolved_by: dict[str, Modality | None] = {}
    comparison: dict[str, dict[str, float]] = {}

    def descend(group: tuple[str, ...], depth: int) -> tuple[tuple[str, ...], ...]:
        if len(group) == 1 or depth >= len(criteria):
            if len(group) > 1:
                for name in group:
                    resolved_by.setdefault(name, None)
            return (group,)

        modality = criteria[depth]
        values = {name: _value(tables, name, modality, period) for name in group}

        # Everyone level on this criterion: nothing was decided here, move on
        # without claiming credit for it.
        if len(set(values.values())) == 1:
            return descend(group, depth + 1)

        snapshot = {
            name: float(value) if value.is_finite() else 0.0
            for name, value in values.items()
        }

        blocks: list[tuple[str, ...]] = []
        for value in sorted(set(values.values()), reverse=True):
            tied = tuple(name for name in group if values[name] == value)
            if len(tied) == 1:
                resolved_by[tied[0]] = modality
                comparison[tied[0]] = snapshot
                blocks.append(tied)
            else:
                for sub_block in descend(tied, depth + 1):
                    for name in sub_block:
                        if resolved_by.get(name) is None and len(sub_block) == 1:
                            resolved_by[name] = modality
                            comparison[name] = snapshot
                    blocks.append(sub_block)
        return tuple(blocks)

    blocks = descend(tuple(names), 0)
    return TiebreakOutcome(
        blocks=blocks,
        resolved_by=resolved_by,
        comparison={name: dict(values) for name, values in comparison.items()},
    )


def order_with_tiebreaks(
    groups: Sequence[tuple[int, Sequence[str]]],
    tables: Tables,
    period: Period,
) -> tuple[list[tuple[int, str, TiebreakInfo | None]], list[tuple[str, ...]]]:
    """Flatten score groups into final positions.

    ``groups`` is ``(score, names)`` already sorted best-score-first. Returns
    the ordered rows as ``(position, name, tiebreak)`` plus every tie the
    cascade could not settle.

    Positions keep competition semantics across the whole table: an unresolved
    pair sharing position 5 is followed by position 7.
    """
    rows: list[tuple[int, str, TiebreakInfo | None]] = []
    unresolved: list[tuple[str, ...]] = []
    position = 1

    for _score, names in groups:
        names = tuple(names)
        if len(names) == 1:
            rows.append((position, names[0], None))
            position += 1
            continue

        outcome = break_tie(names, tables, period)
        for block in outcome.blocks:
            if len(block) > 1:
                unresolved.append(block)
            for name in block:
                others = tuple(other for other in names if other != name)
                info = TiebreakInfo(
                    tied_with=others,
                    resolved_by=outcome.resolved_by.get(name),
                    comparison=outcome.comparison.get(name, {}),
                )
                rows.append((position, name, info))
            position += len(block)

    return rows, unresolved
