"""The monthly tally.

Implements the five rules, in order:

1. Add +20% to the raw calories of anyone carrying the bonus flag, and only
   then sort the calories table. The bonus applies to calories ONLY --
   distance and duration always use the raw value.
2. Drop anyone with 0 hustle points from the monthly tally.
3. Position in each of the three scoring tables uses competition ranking.
4. Monthly score = sum of the three positions. Lowest score leads.
5. Ties fall through the cascade in ``tiebreak``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from .models import (
    SCORING_MODALITIES,
    Exclusion,
    ExclusionReason,
    Modality,
    MonthResult,
    Participant,
    Period,
    Standing,
    Tables,
)
from .ranking import competition_rank, to_decimal
from .tiebreak import order_with_tiebreaks

__all__ = ["CALORIE_BONUS_MULTIPLIER", "adjusted_calories", "tally_month"]

#: Rule 1. Calories only.
CALORIE_BONUS_MULTIPLIER = Decimal("1.2")


def adjusted_calories(raw: float | Decimal, *, bonus: bool) -> Decimal:
    value = to_decimal(raw)
    return value * CALORIE_BONUS_MULTIPLIER if bonus else value


def _roster(participants: Iterable[Participant]) -> dict[str, Participant]:
    return {person.name: person for person in participants}


def _candidates(tables: Tables) -> tuple[str, ...]:
    """Everyone appearing on at least one scoring leaderboard this month.

    Order is deterministic: first appearance across the tables, which keeps
    results stable run to run.
    """
    seen: dict[str, None] = {}
    for modality in SCORING_MODALITIES:
        for entry in tables.get(modality, Period.MONTH):
            seen.setdefault(entry.name, None)
    return tuple(seen)


def _raw_values(
    tables: Tables,
    modality: Modality,
    names: Sequence[str],
) -> dict[str, float]:
    """Values for ``names``, defaulting to 0 when the person is not listed.

    A missing row means the screenshot did not show that person. The review
    screen flags it before anything gets here; treating it as zero keeps the
    tally total rather than crashing on incomplete input.
    """
    listed = {entry.name: entry.value for entry in tables.get(modality, Period.MONTH)}
    return {name: listed.get(name, 0.0) for name in names}


def tally_month(
    month: str,
    tables: Tables,
    participants: Iterable[Participant] = (),
) -> MonthResult:
    """Run the monthly tally.

    ``month`` is ``"YYYY-MM"``. ``tables`` must carry the three scoring
    leaderboards for ``Period.MONTH``, plus distance and duration for the
    tiebreak. Nothing here touches disk or the network.
    """
    roster = _roster(participants)
    candidates = _candidates(tables)

    hustle = _raw_values(tables, Modality.HUSTLE, candidates)

    # Rule 2 -- before ranking, so the excluded do not occupy positions.
    excluded = tuple(
        Exclusion(name=name, reason=ExclusionReason.ZERO_HUSTLE)
        for name in candidates
        if to_decimal(hustle[name]) <= 0
    )
    excluded_names = {item.name for item in excluded}
    ranked = tuple(name for name in candidates if name not in excluded_names)

    if not ranked:
        return MonthResult(month=month, standings=(), excluded=excluded)

    raw_values: dict[Modality, dict[str, float]] = {
        modality: _raw_values(tables, modality, ranked)
        for modality in SCORING_MODALITIES
    }

    # Rule 1 -- bonus first, then sort.
    bonus_applied = {
        name: roster[name].calorie_bonus if name in roster else False for name in ranked
    }
    calories_adjusted: dict[str, Decimal] = {
        name: adjusted_calories(
            raw_values[Modality.CALORIES][name], bonus=bonus_applied[name]
        )
        for name in ranked
    }

    # Rule 3.
    positions: dict[Modality, Mapping[str, int]] = {}
    for modality in SCORING_MODALITIES:
        if modality is Modality.CALORIES:
            pairs = [(name, calories_adjusted[name]) for name in ranked]
        else:
            pairs = [(name, raw_values[modality][name]) for name in ranked]
        positions[modality] = competition_rank(pairs, higher_is_better=True)

    # Rule 4.
    totals = {
        name: sum(positions[modality][name] for modality in SCORING_MODALITIES)
        for name in ranked
    }

    groups: list[tuple[int, list[str]]] = []
    for score in sorted(set(totals.values())):
        groups.append((score, [name for name in ranked if totals[name] == score]))

    # Rule 5.
    ordered, unresolved = order_with_tiebreaks(groups, tables, Period.MONTH)

    standings = tuple(
        Standing(
            position=position,
            name=name,
            total=totals[name],
            positions={modality: positions[modality][name] for modality in SCORING_MODALITIES},
            values={
                Modality.HUSTLE: raw_values[Modality.HUSTLE][name],
                Modality.ACTIVE_DAYS: raw_values[Modality.ACTIVE_DAYS][name],
                Modality.CALORIES: raw_values[Modality.CALORIES][name],
                Modality.DISTANCE: tables.value_for(name, Modality.DISTANCE, Period.MONTH),
                Modality.DURATION: tables.value_for(name, Modality.DURATION, Period.MONTH),
            },
            calories_adjusted=float(calories_adjusted[name]),
            calorie_bonus_applied=bonus_applied[name],
            tiebreak=tiebreak,
        )
        for position, name, tiebreak in ordered
    )

    return MonthResult(
        month=month,
        standings=standings,
        excluded=excluded,
        unresolved_ties=tuple(unresolved),
    )
