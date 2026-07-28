"""What an engine gives back after looking at one screenshot.

``raw_value`` is the string exactly as it was read -- "14,939 calorias",
"221 hr 41 min". This layer never turns it into a number: that is
``core/values.py``, which is domain knowledge about how GymRats formats
things, not about how pixels become characters. Swapping Tesseract for
PaddleOCR must not change how "1,026.13 quilômetros" is understood.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.models import Modality, Period

__all__ = ["ExtractedRow", "Extraction"]


@dataclass(frozen=True)
class ExtractedRow:
    """One person's line on one leaderboard, as read."""

    name: str
    raw_value: str
    #: The rank GymRats printed down the right-hand side. Never scored with --
    #: it exists so the review screen can cross-check it against the order the
    #: values imply, against the RAW order, since the app knows nothing about
    #: the calorie bonus.
    position: int | None = None


@dataclass(frozen=True)
class Extraction:
    """One screenshot, read.

    ``modality`` and ``period`` come from the screenshot's own header, not from
    the filename. ``None`` means the header could not be identified, which
    becomes a ``missing_modality`` or ``missing_period`` issue for the admin to
    settle -- never a guess.
    """

    modality: Modality | None = None
    period: Period | None = None
    rows: tuple[ExtractedRow, ...] = field(default_factory=tuple)
    #: Which screenshot this came from, so the review screen can show it.
    item_id: str | None = None
