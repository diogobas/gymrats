"""Tally core -- pure Python.

Nothing in this package imports FastAPI, OpenCV, Tesseract, or touches the
filesystem. It takes leaderboards already in data structures and returns the
standings. The rules live here, and so do the tests.
"""

from .models import (
    SCORING_MODALITIES,
    TIEBREAK_MODALITIES,
    Entry,
    Exclusion,
    ExclusionReason,
    Modality,
    MonthResult,
    Participant,
    Period,
    SeasonResult,
    SeasonRow,
    Standing,
    Tables,
    TiebreakInfo,
)
from .ranking import competition_rank
from .roster import NameResolution, Roster
from .scoring import CALORIE_BONUS_MULTIPLIER, adjusted_calories, tally_month
from .season import absentee_score, build_season
from .tiebreak import break_tie
from .values import ParseError, parse_duration_minutes, parse_number, parse_value

__all__ = [
    "CALORIE_BONUS_MULTIPLIER",
    "SCORING_MODALITIES",
    "TIEBREAK_MODALITIES",
    "Entry",
    "Exclusion",
    "ExclusionReason",
    "Modality",
    "MonthResult",
    "NameResolution",
    "ParseError",
    "Participant",
    "Period",
    "Roster",
    "SeasonResult",
    "SeasonRow",
    "Standing",
    "Tables",
    "TiebreakInfo",
    "absentee_score",
    "adjusted_calories",
    "break_tie",
    "build_season",
    "competition_rank",
    "parse_duration_minutes",
    "parse_number",
    "parse_value",
    "tally_month",
]
