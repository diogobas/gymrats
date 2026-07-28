"""The engine that reads nothing.

Every screenshot comes back empty, so the review screen opens with the image
on one side and blank rows on the other and the admin types what they see.

That is not a placeholder for its own sake: it closes the loop before any OCR
exists, and it stays useful afterwards as the fallback for a screenshot the
real engine chokes on. Step 4 registers pytesseract next to it; nothing else
in the system changes.
"""

from __future__ import annotations

from .models import Extraction

__all__ = ["ManualEngine"]


class ManualEngine:
    name = "manual"

    def extract(self, image: bytes) -> Extraction:
        return Extraction()
