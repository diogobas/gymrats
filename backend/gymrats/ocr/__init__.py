"""Image bytes in, extracted lines out.

Pluggable and deliberately ignorant: an engine identifies the leaderboard from
the screenshot's own header and hands back the value strings verbatim. What
those strings mean is ``core/values.py``'s business.
"""

from .engine import OcrEngine, OcrError
from .manual import ManualEngine
from .models import ExtractedRow, Extraction
from .registry import DEFAULT_ENGINE, ENGINES, build_engine

__all__ = [
    "DEFAULT_ENGINE",
    "ENGINES",
    "ExtractedRow",
    "Extraction",
    "ManualEngine",
    "OcrEngine",
    "OcrError",
    "build_engine",
]
