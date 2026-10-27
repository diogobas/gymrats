"""Where things live and which plugins are active.

Everything is an environment variable prefixed ``GYMRATS_``, with defaults
that work from a clean checkout: ``GYMRATS_SOURCE=local_folder`` to reprocess a
directory, ``GYMRATS_OCR=tesseract`` once step 4 registers it.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from ..ingestion.registry import DEFAULT_SOURCE
from ..ocr.registry import DEFAULT_ENGINE

__all__ = ["Settings"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GYMRATS_", extra="ignore")

    #: The reviewed leaderboards and the roster. The source of truth.
    data: Path = Path("data")
    #: What the static site reads. Generated, and committed.
    site: Path = Path("frontend/public/data")
    #: Screenshots being worked on. Not versioned.
    inbox: Path = Path("data/inbox")

    private: Path = Path("experiments/gymrats_collector/.local")

    source: str = DEFAULT_SOURCE
    ocr: str = DEFAULT_ENGINE

    #: 0.0.0.0 so the phone on the same wifi can reach it.
    host: str = "0.0.0.0"
    port: int = 8000
