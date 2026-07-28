"""Reading the files under ``data/``.

The only place that knows where things live on disk. Everything it returns is
already a core dataclass.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core.models import MonthResult, Participant, Standing, Tables
from .schema import participants_from_dict, tables_from_dict

__all__ = ["Repository"]


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Repository:
    def __init__(self, root: Path | str = "data"):
        self.root = Path(root)

    # -- participants ------------------------------------------------------

    @property
    def participants_path(self) -> Path:
        return self.root / "participants.json"

    def participants(self) -> tuple[Participant, ...]:
        return participants_from_dict(_read(self.participants_path))

    # -- tallied months ----------------------------------------------------

    def month_path(self, month: str) -> Path:
        return self.root / "months" / f"{month}.json"

    def months(self) -> tuple[str, ...]:
        directory = self.root / "months"
        if not directory.is_dir():
            return ()
        return tuple(sorted(path.stem for path in directory.glob("*.json")))

    def tables(self, month: str) -> Tables:
        return tables_from_dict(_read(self.month_path(month)))

    # -- history -----------------------------------------------------------

    def history(self, year: int) -> dict[str, list[str]]:
        """Finishing orders for months tallied before this system existed.

        Only the order survives for those, which is all the season table
        needs. Returns ``{month: [names in finishing order]}``.
        """
        path = self.root / "history" / f"{year}.json"
        if not path.is_file():
            return {}
        return dict(_read(path).get("ranked", {}))

    def history_results(self, year: int) -> tuple[MonthResult, ...]:
        """History turned into MonthResults carrying positions and nothing else.

        Absences are deliberately not recorded: whoever is missing from a
        month's list did not compete, and ``build_season`` derives their score
        from last place plus one.
        """
        return tuple(
            MonthResult(
                month=month,
                standings=tuple(
                    Standing(
                        position=position,
                        name=name,
                        total=position,
                        positions={},
                        values={},
                        calories_adjusted=0.0,
                        calorie_bonus_applied=False,
                    )
                    for position, name in enumerate(order, start=1)
                ),
            )
            for month, order in sorted(self.history(year).items())
        )
