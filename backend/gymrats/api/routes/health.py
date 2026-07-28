from __future__ import annotations

from fastapi import APIRouter

from ... import __version__
from ..deps import Wiring

router = APIRouter()


@router.get("/health")
def health(services: Wiring) -> dict:
    """Which plugins are actually wired in right now.

    The first thing to check when the phone says something odd: is this the
    upload source, and is any real OCR engine loaded?
    """
    return {
        "status": "ok",
        "version": __version__,
        "source": services.settings.source,
        "ocr_engine": services.engine.name,
        "data": str(services.settings.data),
        "site": str(services.settings.site),
        "inbox": str(services.settings.inbox),
    }
