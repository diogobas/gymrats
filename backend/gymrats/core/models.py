"""Domain model for the tally.

This module -- and every other module under ``core`` -- is plain Python. No
FastAPI, no OpenCV, no filesystem, no network. Anything that reaches the core
has already been turned into these types by an outer layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping


class Modality(str, Enum):
    """The five leaderboards GymRats shows."""

    HUSTLE = "hustle"
    ACTIVE_DAYS = "active_days"
    CALORIES = "calories"
    DISTANCE = "distance"
    DURATION = "duration"


#: The three that add up to the monthly score.
SCORING_MODALITIES: tuple[Modality, ...] = (
    Modality.HUSTLE,
    Modality.ACTIVE_DAYS,
    Modality.CALORIES,
)

#: The tiebreak cascade, in the order it is applied.
TIEBREAK_MODALITIES: tuple[Modality, ...] = (Modality.DISTANCE, Modality.DURATION)


class Period(str, Enum):
    """Which time slice a leaderboard screenshot covers."""

    MONTH = "month"  # "Este mês"
    YEAR = "year"  # "Este ano"


class ExclusionReason(str, Enum):
    ZERO_HUSTLE = "zero_hustle"


@dataclass(frozen=True)
class Participant:
    """A registered competitor.

    ``name`` is the canonical name used in every table. ``aliases`` carries the
    longer profile names GymRats displays, so "Andressa Barcelos Aires Barros"
    resolves to "Andressa".
    """

    name: str
    aliases: tuple[str, ...] = ()
    calorie_bonus: bool = False


@dataclass(frozen=True)
class Entry:
    """One person's value on one leaderboard.

    ``reported_position`` is the rank GymRats printed down the right-hand side
    of the screenshot. The core never scores with it -- it only exists so the
    review screen can cross-check it against the order computed from the
    values and flag OCR mistakes.
    """

    name: str
    value: float
    reported_position: int | None = None


@dataclass(frozen=True)
class Tables:
    """Every leaderboard for one month, keyed by ``(modality, period)``."""

    data: Mapping[tuple[Modality, Period], tuple[Entry, ...]] = field(
        default_factory=dict
    )

    @classmethod
    def build(
        cls,
        raw: Mapping[tuple[Modality, Period], Iterable[Entry]],
    ) -> "Tables":
        return cls({key: tuple(entries) for key, entries in raw.items()})

    def get(self, modality: Modality, period: Period = Period.MONTH) -> tuple[Entry, ...]:
        return self.data.get((modality, period), ())

    def has(self, modality: Modality, period: Period = Period.MONTH) -> bool:
        return bool(self.get(modality, period))

    def value_for(
        self,
        name: str,
        modality: Modality,
        period: Period = Period.MONTH,
    ) -> float | None:
        for entry in self.get(modality, period):
            if entry.name == name:
                return entry.value
        return None

    def names(self, modality: Modality, period: Period = Period.MONTH) -> tuple[str, ...]:
        return tuple(entry.name for entry in self.get(modality, period))


@dataclass(frozen=True)
class TiebreakInfo:
    """Why two people with the same score ended up in this order.

    ``resolved_by`` is ``None`` when the cascade ran out of criteria and the
    tie stands -- rule 5c says do not invent a winner in that case.

    The core deliberately emits no prose here. The published JSON renders the
    sentence from these fields, so presentation stays out of the domain.
    """

    tied_with: tuple[str, ...]
    resolved_by: Modality | None
    comparison: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Standing:
    """One row of the monthly result."""

    position: int
    name: str
    total: int
    positions: Mapping[Modality, int]
    values: Mapping[Modality, float | None]
    calories_adjusted: float
    calorie_bonus_applied: bool
    tiebreak: TiebreakInfo | None = None


@dataclass(frozen=True)
class Exclusion:
    name: str
    reason: ExclusionReason


@dataclass(frozen=True)
class MonthResult:
    month: str  # "YYYY-MM"
    standings: tuple[Standing, ...]
    excluded: tuple[Exclusion, ...] = ()
    unresolved_ties: tuple[tuple[str, ...], ...] = ()

    @property
    def ranked_count(self) -> int:
        return len(self.standings)

    @property
    def last_position(self) -> int:
        """Highest position number actually handed out this month.

        This is what an absentee's season column is built from: last place
        plus one. It equals ``ranked_count`` unless an unresolved tie left a
        position number unused at the bottom of the table.
        """
        return max((row.position for row in self.standings), default=0)

    def position_of(self, name: str) -> int | None:
        for row in self.standings:
            if row.name == name:
                return row.position
        return None


@dataclass(frozen=True)
class SeasonRow:
    position: int
    name: str
    total: int
    by_month: Mapping[str, int]
    imputed_months: tuple[str, ...] = ()
    tiebreak: TiebreakInfo | None = None


@dataclass(frozen=True)
class SeasonResult:
    year: int
    months: tuple[str, ...]
    rows: tuple[SeasonRow, ...]
    unresolved_ties: tuple[tuple[str, ...], ...] = ()
