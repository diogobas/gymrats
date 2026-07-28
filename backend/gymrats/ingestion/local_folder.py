"""Screenshots already sitting in a directory.

Useful for two things: re-running a month whose images are on the laptop, and
tests -- a fixture directory is a working source with no HTTP involved.

The batch is the directory. Anything already read has moved into
``processed/`` and is no longer pending.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ._files import PROCESSED_DIR, content_type_for, images_in, timestamp, within
from .models import ScreenshotItem
from .source import UnknownItem

__all__ = ["LocalFolderSource"]


class LocalFolderSource:
    name = "local_folder"

    def __init__(self, folder: Path | str = "data/inbox"):
        self.folder = Path(folder)

    @property
    def batch_id(self) -> str:
        return self.folder.name or "local_folder"

    def list_pending(self) -> list[ScreenshotItem]:
        return [
            ScreenshotItem(
                id=path.name,
                batch=self.batch_id,
                filename=path.name,
                size=path.stat().st_size,
                received_at=timestamp(
                    datetime.fromtimestamp(path.stat().st_mtime).astimezone()
                ),
                content_type=content_type_for(path),
            )
            for path in images_in(self.folder)
        ]

    def fetch(self, item: ScreenshotItem) -> bytes:
        return self._path(item).read_bytes()

    def mark_processed(self, item: ScreenshotItem) -> None:
        path = self._path(item)
        done = self.folder / PROCESSED_DIR
        done.mkdir(parents=True, exist_ok=True)
        path.replace(done / path.name)

    def _path(self, item: ScreenshotItem) -> Path:
        path = within(self.folder, item.id)
        if not path.is_file():
            raise UnknownItem(f"print desconhecido: {item.id}")
        return path
