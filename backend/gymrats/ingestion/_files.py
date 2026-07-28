"""Filesystem odds and ends shared by the two local sources.

Both of them happen to keep screenshots in directories. That is an
implementation detail of these two sources, not part of the contract -- a
remote source would keep none of this.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .source import UnknownItem

__all__ = [
    "IMAGE_SUFFIXES",
    "PROCESSED_DIR",
    "content_type_for",
    "images_in",
    "safe_name",
    "suffix_for",
    "timestamp",
    "within",
]

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp"})

#: Processed screenshots move here instead of being deleted -- a tally that has
#: to be redone needs them.
PROCESSED_DIR = "processed"

_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".webp": "image/webp",
}

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str, *, fallback: str = "print") -> str:
    """Flatten anything a phone might send into a plain filename.

    Item identifiers end up in a URL and then back in a path, so they are
    built from this rather than trusted.
    """
    cleaned = _UNSAFE.sub("-", (name or "").strip()).strip("-.")
    return cleaned or fallback


def within(root: Path, name: str) -> Path:
    """Resolve ``name`` directly under ``root``, or refuse.

    The API takes batch and item identifiers straight from the URL. Anything
    that tries to climb out is not a missing file, it is an attack.
    """
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise UnknownItem(f"identificador inválido: {name!r}")
    candidate = (root / name).resolve()
    if candidate.parent != root.resolve():
        raise UnknownItem(f"identificador inválido: {name!r}")
    return candidate


def images_in(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def content_type_for(path: Path) -> str | None:
    return _CONTENT_TYPES.get(path.suffix.lower())


def suffix_for(content_type: str | None) -> str | None:
    """The extension that goes with a MIME type, if it is one we accept."""
    wanted = (content_type or "").split(";")[0].strip().lower()
    for suffix, known in _CONTENT_TYPES.items():
        if known == wanted:
            return suffix
    return None


def timestamp(moment: datetime | None = None) -> str:
    return (moment or datetime.now()).astimezone().isoformat(timespec="seconds")
