"""Short name -> screenshot source.

``GYMRATS_SOURCE`` names one of these. Adding a source means adding a line
here and nothing else; see ``source.py`` for the three methods it owes.

Only local sources are implemented. A remote one -- Telegram, Dropbox, Drive
-- fits the same contract: ``fetch`` returns bytes, the identifier stays
opaque, and no layer above ingestion changes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .local_folder import LocalFolderSource
from .source import ScreenshotSource
from .upload import DEFAULT_INBOX, UploadSource

__all__ = ["SOURCES", "build_source"]

SOURCES: dict[str, Callable[[Path], ScreenshotSource]] = {
    "upload": lambda inbox: UploadSource(inbox),
    "local_folder": lambda folder: LocalFolderSource(folder),
}

DEFAULT_SOURCE = "upload"


def build_source(name: str, directory: Path | str = DEFAULT_INBOX) -> ScreenshotSource:
    try:
        factory = SOURCES[name]
    except KeyError:
        known = ", ".join(sorted(SOURCES))
        raise ValueError(f"fonte desconhecida: {name!r} (conhecidas: {known})") from None
    return factory(Path(directory))
