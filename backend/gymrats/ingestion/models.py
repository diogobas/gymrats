"""What a screenshot looks like before anyone has read it.

The identifier is opaque on purpose. It belongs to whichever source produced
it -- a filename here, a Telegram ``message_id`` or a Drive file ID in a source
that does not exist yet -- and nothing outside ``ingestion`` may take it apart.
That is what lets a new source arrive without OCR, the tally or the site
noticing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Batch", "ScreenshotItem"]


@dataclass(frozen=True)
class ScreenshotItem:
    """One screenshot waiting to be read."""

    id: str
    batch: str
    filename: str | None = None
    size: int = 0
    received_at: str | None = None  # ISO 8601
    content_type: str | None = None


@dataclass(frozen=True)
class Batch:
    """The screenshots that arrived together.

    A month's tally is one batch: ten or so screenshots picked from the camera
    roll in a single go.
    """

    id: str
    items: tuple[ScreenshotItem, ...] = field(default_factory=tuple)
