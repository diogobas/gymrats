"""Reading the files under ``data/``.

The only place that knows where things live on disk. Everything it returns is
already a core dataclass.
"""

from __future__ import annotations

import calendar
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ..core.models import MonthResult, Participant, Standing, Tables
from .schema import (
    SCHEMA_VERSION,
    participants_from_dict,
    participants_to_dict,
    tables_from_dict,
    tables_to_dict,
)

__all__ = ["Repository"]


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _notes(path: Path) -> dict[str, Any]:
    """The hand-written notes already in a file.

    Keys starting with "_" are comments the admin wrote for themselves. These
    files are meant to be opened and edited by hand, so rewriting one from the
    API must not wipe what is not machine-readable.
    """
    if not path.is_file():
        return {}
    return {key: value for key, value in _read(path).items() if key.startswith("_")}


def _write(path: Path, document: Mapping[str, Any]) -> Path:
    """Overwrite ``path``, carrying the existing notes over.

    Notes are re-inserted just after ``schema_version``, where they were, so
    the file the admin reopens next month still reads the way they wrote it.
    """
    notes = _notes(path)
    merged: dict[str, Any] = {}
    for key, value in document.items():
        merged[key] = value
        if key == "schema_version":
            merged.update(notes)
    for key, value in notes.items():
        merged.setdefault(key, value)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


class Repository:
    def __init__(self, root: Path | str = "data"):
        self.root = Path(root)

    # -- participants ------------------------------------------------------

    @property
    def participants_path(self) -> Path:
        return self.root / "participants.json"

    def participants(self) -> tuple[Participant, ...]:
        return participants_from_dict(_read(self.participants_path))

    def write_participants(self, participants: Iterable[Participant]) -> Path:
        return _write(self.participants_path, participants_to_dict(participants))

    # -- tallied months ----------------------------------------------------

    def month_path(self, month: str) -> Path:
        return self.root / "months" / f"{month}.json"

    def months(self) -> tuple[str, ...]:
        directory = self.root / "months"
        if not directory.is_dir():
            return ()
        return tuple(sorted(path.stem for path in directory.glob("*.json")))

    def months_of(self, year: int) -> tuple[str, ...]:
        return tuple(month for month in self.months() if month.startswith(f"{year}-"))

    def tables(self, month: str) -> Tables:
        return tables_from_dict(_read(self.month_path(month)))

    def write_tables(self, month: str, tables: Tables) -> Path:
        """Store the reviewed leaderboards -- the source of truth for a month.

        Everything published is recomputed from this file, so committing a
        tally means writing this and nothing else about the result.
        """
        return _write(
            self.month_path(month),
            {
                "schema_version": SCHEMA_VERSION,
                "month": month,
                **({"ignore_hustle": True} if tables.ignore_hustle else {}),
                "tables": tables_to_dict(tables),
            },
        )

    # Current-month snapshots are stored separately from closed months.
    def provisional_path(self, month: str) -> Path:
        return self.root / "previews" / f"{month}.json"

    def provisional_months(self) -> tuple[str, ...]:
        closed = set(self.months())
        return tuple(
            sorted(
                p.stem
                for p in (self.root / "previews").glob("*.json")
                if p.stem not in closed
            )
        )

    def published_months(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.months()) | set(self.provisional_months())))

    def public_tables(self, month: str) -> Tables:
        if month in self.months():
            return self.tables(month)
        return tables_from_dict(_read(self.provisional_path(month)))

    def provisional_info(self, month: str) -> dict:
        if month not in self.provisional_months():
            return {}
        doc = _read(self.provisional_path(month))
        info = {"provisional": True, "data_through": doc["provenance"]["monthly_end"]}
        if doc["provenance"].get("pending_review"):
            info["pending_review"] = True
        return info

    def complete_provisional_months(self) -> tuple[str, ...]:
        return tuple(
            month
            for month in self.provisional_months()
            if self.provisional_info(month)["data_through"]
            == f"{month}-{calendar.monthrange(int(month[:4]), int(month[-2:]))[1]:02d}"
        )

    def write_provisional(self, month: str, tables: Tables) -> Path:
        return _write(
            self.provisional_path(month),
            {
                "schema_version": SCHEMA_VERSION,
                "month": month,
                "provisional": True,
                "tables": tables_to_dict(tables),
            },
        )

    # -- history -----------------------------------------------------------

    def history_years(self) -> tuple[int, ...]:
        directory = self.root / "history"
        if not directory.is_dir():
            return ()
        return tuple(sorted(int(path.stem) for path in directory.glob("*.json")))

    def years(self) -> tuple[int, ...]:
        """Every season with data, tallied or hand-recorded."""
        from_months = {int(month[:4]) for month in self.published_months()}
        return tuple(sorted(from_months | set(self.history_years())))

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
