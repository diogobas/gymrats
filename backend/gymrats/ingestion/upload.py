"""Screenshots posted from the phone's browser. The default source.

The main flow: pick ten screenshots from the camera roll, they arrive as one
multipart request, they become one batch. Bytes land under ``data/inbox/``,
which is deliberately not versioned -- the reviewed leaderboards under
``data/months/`` are the source of truth, the images are working material.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from ._files import (
    IMAGE_SUFFIXES,
    PROCESSED_DIR,
    content_type_for,
    images_in,
    safe_name,
    suffix_for,
    timestamp,
    within,
)
from .models import Batch, ScreenshotItem
from .source import UnknownItem

__all__ = ["DEFAULT_INBOX", "IncomingFile", "UploadSource"]

DEFAULT_INBOX = Path("data/inbox")


class IncomingFile:
    """One part of a multipart upload, already read into memory.

    Phone screenshots are a couple of megabytes; there is one admin and one
    upload a month. Streaming to disk would buy nothing.
    """

    def __init__(
        self, filename: str | None, content: bytes, content_type: str | None = None
    ):
        self.filename = filename
        self.content = content
        self.content_type = content_type


class UploadSource:
    """A ``ScreenshotSource`` fed by the API.

    ``receive`` is deliberately outside the protocol: only the upload route
    calls it, and no other source has an equivalent.
    """

    name = "upload"

    def __init__(self, inbox: Path | str = DEFAULT_INBOX):
        self.inbox = Path(inbox)

    # -- receiving ---------------------------------------------------------

    def receive(
        self,
        files: Iterable[IncomingFile],
        *,
        batch_id: str | None = None,
        now: datetime | None = None,
    ) -> Batch:
        moment = now or datetime.now()
        batch = batch_id or moment.strftime("%Y%m%d-%H%M%S")
        directory = self.inbox / safe_name(batch, fallback="batch")
        directory.mkdir(parents=True, exist_ok=True)

        items: list[ScreenshotItem] = []
        for index, incoming in enumerate(files, start=1):
            # The identifier is built here, never taken from the phone: it
            # travels through a URL and comes back as a path segment.
            item_id = f"{index:02d}-{self._name_for(incoming)}"
            path = directory / item_id
            path.write_bytes(incoming.content)
            items.append(
                ScreenshotItem(
                    id=item_id,
                    batch=directory.name,
                    filename=incoming.filename,
                    size=len(incoming.content),
                    received_at=timestamp(moment),
                    content_type=incoming.content_type or content_type_for(path),
                )
            )

        return Batch(id=directory.name, items=tuple(items))

    # -- the protocol ------------------------------------------------------

    def list_pending(self) -> list[ScreenshotItem]:
        if not self.inbox.is_dir():
            return []
        pending: list[ScreenshotItem] = []
        for directory in sorted(self.inbox.iterdir()):
            if directory.is_dir():
                pending.extend(self._items_in(directory))
        return pending

    def fetch(self, item: ScreenshotItem) -> bytes:
        return self._path(item).read_bytes()

    def mark_processed(self, item: ScreenshotItem) -> None:
        path = self._path(item)
        done = path.parent / PROCESSED_DIR
        done.mkdir(exist_ok=True)
        path.replace(done / path.name)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _name_for(incoming: IncomingFile) -> str:
        """A safe filename that still ends in an image extension.

        The extension is not cosmetic: it is how a stored screenshot is
        recognised as one later. Phones do send parts with no filename at all.
        """
        original = Path(incoming.filename or "")
        suffix = original.suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            suffix = suffix_for(incoming.content_type) or ".png"
        return f"{safe_name(original.stem, fallback='print')}{suffix}"

    def _items_in(self, directory: Path) -> list[ScreenshotItem]:
        return [
            ScreenshotItem(
                id=path.name,
                batch=directory.name,
                filename=path.name,
                size=path.stat().st_size,
                received_at=timestamp(
                    datetime.fromtimestamp(path.stat().st_mtime).astimezone()
                ),
                content_type=content_type_for(path),
            )
            for path in images_in(directory)
        ]

    def _path(self, item: ScreenshotItem) -> Path:
        directory = within(self.inbox, item.batch)
        path = within(directory, item.id)
        if not path.is_file():
            raise UnknownItem(f"print desconhecido: {item.batch}/{item.id}")
        return path
