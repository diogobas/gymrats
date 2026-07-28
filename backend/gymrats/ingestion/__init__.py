"""Where the screenshots come from.

Bytes and an opaque identifier. Nothing above this layer knows whether they
arrived from a phone, a directory, or somewhere that does not exist yet.
"""

from .local_folder import LocalFolderSource
from .models import Batch, ScreenshotItem
from .registry import DEFAULT_SOURCE, SOURCES, build_source
from .source import ScreenshotSource, SourceError, UnknownItem
from .upload import DEFAULT_INBOX, IncomingFile, UploadSource

__all__ = [
    "DEFAULT_INBOX",
    "DEFAULT_SOURCE",
    "SOURCES",
    "Batch",
    "IncomingFile",
    "LocalFolderSource",
    "ScreenshotItem",
    "ScreenshotSource",
    "SourceError",
    "UnknownItem",
    "UploadSource",
    "build_source",
]
