"""What the review screen sends back.

Responses are the dicts ``storage/schema.py`` already builds -- the same
shapes, rendered in one place. Only the incoming bodies are declared here,
because those need validating.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..core.models import Modality, Period

__all__ = [
    "DraftIn",
    "DraftRowIn",
    "DraftTableIn",
    "ParticipantIn",
    "ParticipantPatch",
    "TallyIn",
]


class ParticipantIn(BaseModel):
    name: str = Field(min_length=1)
    aliases: list[str] = []
    calorie_bonus: bool = False


class ParticipantPatch(BaseModel):
    """Everything optional: the screen edits one field at a time."""

    aliases: list[str] | None = None
    calorie_bonus: bool | None = None


class DraftRowIn(BaseModel):
    name: str = ""
    raw_value: str = ""
    #: The rank printed on the screenshot, kept for the cross-check.
    position: int | None = None


class DraftTableIn(BaseModel):
    modality: Modality | None = None
    period: Period | None = None
    rows: list[DraftRowIn] = []
    sources: list[str] = []


class DraftIn(BaseModel):
    """A corrected draft on its way back.

    Resolved names, parsed values and issues are deliberately absent: they are
    recomputed from these rows, so the screen cannot send back a verdict that
    contradicts the roster as it stands now.
    """

    month: str | None = None
    tables: list[DraftTableIn] = []


class TallyIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    draft: DraftIn
    #: The batch whose screenshots this came from, so committing can retire
    #: them. Absent when a draft was assembled by hand.
    batch: str | None = None
