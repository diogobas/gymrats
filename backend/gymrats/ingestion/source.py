"""The contract every screenshot source implements.

Three methods, and ``fetch`` returns bytes. No layer above this one is allowed
to assume a file path exists, which is the whole reason a remote source can be
added later without touching OCR, the tally or the site.

To add one:

1. write ``ingestion/<your_source>.py`` with a class satisfying
   ``ScreenshotSource``;
2. register it in ``ingestion/registry.py`` under a short name;
3. point ``GYMRATS_SOURCE`` at that name.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import ScreenshotItem

__all__ = ["ScreenshotSource", "SourceError", "UnknownItem"]


class SourceError(RuntimeError):
    """The source could not do what was asked."""


class UnknownItem(SourceError):
    """No such item -- already processed, or never existed."""


@runtime_checkable
class ScreenshotSource(Protocol):
    def list_pending(self) -> list[ScreenshotItem]:
        """Everything waiting to be read, oldest first."""
        ...

    def fetch(self, item: ScreenshotItem) -> bytes:
        """The image itself. Bytes, never a path."""
        ...

    def mark_processed(self, item: ScreenshotItem) -> None:
        """Take it out of the pending list.

        Implementations move rather than delete: a tally that has to be redone
        needs the screenshots it was made from.
        """
        ...
