"""The contract every OCR engine implements.

One method, taking bytes. An engine never sees a file path, never reads
configuration about which month is being tallied, and never converts a value
into a number.

To add one: write ``ocr/<engine>.py`` with a class satisfying ``OcrEngine``,
register it in ``ocr/registry.py``, and point ``GYMRATS_OCR`` at the name.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import Extraction

__all__ = ["OcrEngine", "OcrError"]


class OcrError(RuntimeError):
    """The engine could not read the image at all.

    A partially read screenshot is not an error -- it is a screenshot with
    issues, which is what the review screen is for.
    """


@runtime_checkable
class OcrEngine(Protocol):
    name: str

    def extract(self, image: bytes) -> Extraction:
        """Read one screenshot."""
        ...
