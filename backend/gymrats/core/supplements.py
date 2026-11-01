"""Recalculate API rankings with documented positions for missing participants."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import replace

from .models import (
    SCORING_MODALITIES,
    Modality,
    MonthResult,
    Participant,
    Period,
    Standing,
    Tables,
)
from .ranking import competition_rank
from .tiebreak import order_with_tiebreaks


def insert_position(positions: dict[str, int], name: str, position: int) -> None:
    """Insert an unknown value at a known distinct rank, preserving API ties."""
    if (
        position < 1
        or sum(rank < position for rank in positions.values()) != position - 1
    ):
        raise ValueError("Historical position would split a tie or skip participants")
    for other, rank in positions.items():
        if rank >= position:
            positions[other] = rank + 1
    positions[name] = position


def tally_supplemented(
    month: str, tables: Tables, participants: Iterable[Participant]
) -> MonthResult:
    from .scoring import adjusted_calories, tally_month

    participants = tuple(participants)
    roster = {person.name: person for person in participants}
    if tables.ignore_hustle or tables.official_result is not None:
        raise ValueError("Historical supplements require the standard API scoring rules")
    base = tally_month(month, replace(tables, supplements=()), participants)
    source_names = {row.name for rows in tables.data.values() for row in rows}
    supplements = {item.name: item for item in tables.supplements}
    if len(supplements) != len(tables.supplements):
        raise ValueError("Duplicate historical participant")
    for name, item in supplements.items():
        if (
            not name
            or name in source_names
            or name not in roster
            or not item.source_url
            or not item.note
            or set(item.positions) != {Modality.HUSTLE, Modality.ACTIVE_DAYS}
            or any(type(rank) is not int or rank <= 0 for rank in item.positions.values())
            or Modality.CALORIES not in item.values
            or any(
                not math.isfinite(value) or value < 0 for value in item.values.values()
            )
        ):
            raise ValueError(
                "Invalid historical supplement or participant already in API"
            )
    names = tuple(row.name for row in base.standings) + tuple(supplements)
    values = {row.name: dict(row.values) for row in base.standings}
    values.update(
        {
            name: {metric: item.values.get(metric) for metric in Modality}
            for name, item in supplements.items()
        }
    )
    bonus = {
        name: roster[name].calorie_bonus if name in roster else False for name in names
    }
    calories = {
        name: adjusted_calories(values[name][Modality.CALORIES], bonus=bonus[name])
        for name in names
    }
    positions = {}
    for metric in SCORING_MODALITIES:
        known = [
            (
                name,
                calories[name] if metric == Modality.CALORIES else values[name][metric],
            )
            for name in names
            if values[name][metric] is not None
        ]
        ranks = competition_rank(known)
        missing = sorted(
            (item.positions[metric], name)
            for name, item in supplements.items()
            if values[name][metric] is None
        )
        for rank, name in missing:
            insert_position(ranks, name, rank)
        for name, item in supplements.items():
            if metric in item.positions and ranks[name] != item.positions[metric]:
                raise ValueError("Inferred value disagrees with the historical position")
        positions[metric] = ranks
    totals = {name: sum(ranks[name] for ranks in positions.values()) for name in names}
    groups = [
        (score, [name for name in names if totals[name] == score])
        for score in sorted(set(totals.values()))
    ]
    ordered, unresolved = order_with_tiebreaks(groups, tables, Period.MONTH)
    return MonthResult(
        month=month,
        standings=tuple(
            Standing(
                position=rank,
                name=name,
                total=totals[name],
                positions={metric: ranks[name] for metric, ranks in positions.items()},
                values=values[name],
                calories_adjusted=float(calories[name]),
                calorie_bonus_applied=bonus[name],
                tiebreak=tiebreak,
            )
            for rank, name, tiebreak in ordered
        ),
        excluded=base.excluded,
        unresolved_ties=tuple(unresolved),
        supplements=tables.supplements,
    )
