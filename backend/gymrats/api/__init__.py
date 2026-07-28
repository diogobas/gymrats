"""FastAPI. Orchestration only -- the rules live in the layers below.

Importing this module pulls in FastAPI; nothing in ``core``, ``review`` or
``storage`` does, which is why the tally suite runs without it installed.
"""

from .app import create_app
from .config import Settings

__all__ = ["Settings", "create_app"]
