"""The half-corrected draft, kept on disk.

The review happens on a phone, standing up, across ten leaderboards. Safari
discards background tabs, and losing twenty corrections to that is worse than
keeping a file next to the screenshots it describes -- which are already
there, in the same directory, untracked by git.

Only what the admin typed is stored. Names resolved, values parsed and issues
found are all recomputed on load, so a draft written before a participant was
registered cannot carry a stale verdict back in.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..review.models import Draft
from .schema import draft_from_dict, draft_to_dict

__all__ = ["DraftStore"]

DRAFT_FILENAME = "draft.json"


class DraftStore:
    def __init__(self, root: Path | str = "data/inbox"):
        self.root = Path(root)

    def path(self, batch: str) -> Path:
        # The batch identifier reaches here from a URL. Sources validate it
        # before anything is read; this only ever appends one segment.
        return self.root / batch / DRAFT_FILENAME

    def load(self, batch: str) -> Draft | None:
        path = self.path(batch)
        if not path.is_file():
            return None
        return draft_from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, batch: str, draft: Draft) -> Path:
        path = self.path(batch)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(draft_to_dict(draft), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def clear(self, batch: str) -> None:
        self.path(batch).unlink(missing_ok=True)
