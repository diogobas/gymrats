"""The draft the admin corrects before a month is tallied.

Plain Python, like ``core``: no FastAPI, no OCR engine, no filesystem. It sits
between the two because reviewing has rules of its own -- merging the parts of
a split leaderboard, resolving aliases, cross-checking the app's own numbering
-- and none of them belong to the tally or to the engine that read the pixels.

Nothing here renders a sentence. Issues are structured; the API turns them
into the Portuguese the review screen shows, the same way ``storage/schema.py``
renders the tiebreak.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..core.models import Modality, Period

__all__ = ["Draft", "DraftRow", "DraftTable", "Issue", "IssueType"]


class IssueType(StrEnum):
    """The closed set of things that can be wrong with a draft.

    None of them blocks a commit. The admin is the final authority; the review
    screen only insists on being looked at.
    """

    #: The order the values imply disagrees with the rank the app printed.
    POSITION_MISMATCH = "position_mismatch"
    #: The name is not on the roster and was NOT guessed.
    UNKNOWN_NAME = "unknown_name"
    #: The value string could not be read as a number. Never becomes a zero.
    UNPARSED_VALUE = "unparsed_value"
    #: The same person twice on one leaderboard, with different values.
    DUPLICATE_NAME = "duplicate_name"
    #: The screenshot's header did not say which leaderboard this is.
    MISSING_MODALITY = "missing_modality"
    #: ... nor whether it is "Este mês" or "Este ano".
    MISSING_PERIOD = "missing_period"


@dataclass(frozen=True)
class Issue:
    type: IssueType
    modality: Modality | None = None
    period: Period | None = None
    #: Index into the table's rows, when the problem is one row's.
    row: int | None = None
    name: str | None = None
    #: For POSITION_MISMATCH: what the values imply against what the app said.
    expected: int | None = None
    reported: int | None = None
    #: For UNPARSED_VALUE: the string that could not be read.
    raw_value: str | None = None


@dataclass(frozen=True)
class DraftRow:
    """One line, as read and as understood.

    ``name`` is what was on the screen; ``resolved_name`` is who that is on the
    roster, or ``None`` when nobody knows. ``value`` is ``raw_value`` parsed,
    or ``None`` when it could not be.
    """

    name: str
    raw_value: str
    position: int | None = None
    resolved_name: str | None = None
    value: float | None = None


@dataclass(frozen=True)
class DraftTable:
    modality: Modality | None
    period: Period | None
    rows: tuple[DraftRow, ...] = field(default_factory=tuple)
    #: The screenshots this table was built from -- two when the list did not
    #: fit on one screen.
    sources: tuple[str, ...] = field(default_factory=tuple)

    @property
    def key(self) -> str:
        """A stable identifier for the UI: "calories/month"."""
        return f"{self.modality or '?'}/{self.period or '?'}"


@dataclass(frozen=True)
class Draft:
    month: str | None = None
    tables: tuple[DraftTable, ...] = field(default_factory=tuple)
    issues: tuple[Issue, ...] = field(default_factory=tuple)

    @property
    def is_clean(self) -> bool:
        return not self.issues
