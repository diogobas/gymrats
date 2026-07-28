"""Short name -> OCR engine.

``GYMRATS_OCR`` names one of these. Only ``manual`` exists so far; pytesseract
with OpenCV preprocessing is step 4, and PaddleOCR, EasyOCR or the macOS
Vision framework would each be one more line here.
"""

from __future__ import annotations

from collections.abc import Callable

from .engine import OcrEngine
from .manual import ManualEngine

__all__ = ["DEFAULT_ENGINE", "ENGINES", "build_engine"]

ENGINES: dict[str, Callable[[], OcrEngine]] = {
    "manual": ManualEngine,
}

DEFAULT_ENGINE = "manual"


def build_engine(name: str) -> OcrEngine:
    try:
        factory = ENGINES[name]
    except KeyError:
        known = ", ".join(sorted(ENGINES))
        raise ValueError(f"motor desconhecido: {name!r} (conhecidos: {known})") from None
    return factory()
