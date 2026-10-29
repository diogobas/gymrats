"""Tallying a month that has not been written yet, and then writing it.

The preview exists so the admin sees the standings *before* anything touches
``data/``: the same numbers, computed the same way, with the month that is
still a draft slotted into the season alongside the ones already on disk.

Committing is the only path that writes, and it does three things in order:
store the reviewed leaderboards, republish the site's JSON, and hand back the
result. If the first step fails, nothing was published.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ..core.models import MonthResult, SeasonResult, Tables
from ..core.scoring import tally_month
from ..core.season import build_season
from .publisher import Publisher
from .repository import Repository

__all__ = ["CommitResult", "TallyPreview", "TallyService"]


@dataclass(frozen=True)
class TallyPreview:
    month: MonthResult
    season: SeasonResult


@dataclass(frozen=True)
class CommitResult:
    month: MonthResult
    season: SeasonResult
    month_path: Path
    published: tuple[Path, ...]


class TallyService:
    def __init__(self, repo: Repository, publisher: Publisher | None = None):
        self.repo = repo
        self.publisher = publisher or Publisher(repo)

    def preview(
        self, month: str, tables: Tables, *, include_provisional=False
    ) -> TallyPreview:
        """What committing would produce, without producing it."""
        participants = self.repo.participants()
        tables = self.repo.scope_tables(month, tables)
        result = tally_month(month, tables, participants)
        year = int(month[:4])

        known = set(self.repo.months_of(year))
        if include_provisional:
            known.update(self.repo.complete_provisional_months())
        detailed = {key for key in known if key < month and key.startswith(f"{year}-")}
        results = [
            r
            for r in self.repo.history_results(year)
            if r.month < month and r.month not in detailed
        ]
        results.extend(
            tally_month(key, self.repo.public_tables(key), participants)
            for key in sorted(detailed)
        )
        return TallyPreview(
            month=result,
            season=build_season(
                year, [*results, result], tables, **self.repo.season_options(year)
            ),
        )

    def missing_months(self, month: str, *, include_provisional=False) -> list[str]:
        year = int(month[:4])
        present = set(self.repo.months_of(year)) | set(self.repo.history(year))
        if include_provisional:
            present.update(self.repo.complete_provisional_months())
        return [
            f"{year}-{m:02d}"
            for m in range(1, int(month[-2:]))
            if f"{year}-{m:02d}" not in present
        ]

    def differences(self, month: str, tables: Tables) -> list[dict]:
        if month not in self.repo.published_months():
            return []
        previous = self.repo.public_tables(month)
        differences = []
        for key in sorted(tables.data.keys() | previous.data.keys()):
            modality, period = key
            names = set(tables.names(*key)) | set(previous.names(*key))
            for name in sorted(names):
                old = previous.value_for(name, *key)
                new = tables.value_for(name, *key)
                if old is None or new is None or Decimal(str(old)) != Decimal(str(new)):
                    differences.append(
                        dict(
                            name=name,
                            metric=modality.value,
                            period=period.value,
                            previous=old,
                            collected=new,
                        )
                    )
        return differences

    def commit(
        self, month: str, tables: Tables, *, provenance=None, provisional=False
    ) -> CommitResult:
        # Calculate before writing. Stage a full publication against a private
        # copy so invalid existing data cannot leave a half-published site.
        preview = self.preview(month, tables, include_provisional=provisional)
        if provisional and month in self.repo.months():
            raise ValueError(
                "A closed month cannot be replaced by a provisional snapshot"
            )
        if provisional and (not provenance or not provenance.get("monthly_end")):
            raise ValueError("A provisional snapshot requires an explicit cutoff")
        month_path = (
            self.repo.provisional_path(month)
            if provisional
            else self.repo.month_path(month)
        )
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            shutil.copytree(
                self.repo.root,
                stage / "data",
                ignore=shutil.ignore_patterns("inbox", ".local"),
            )
            staged_repo = Repository(stage / "data")
            staged_path = (
                staged_repo.write_provisional(month, tables)
                if provisional
                else staged_repo.write_tables(month, tables)
            )
            if provenance is not None:
                path = staged_path
                doc = json.loads(path.read_text())
                doc["provenance"] = provenance
                path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
            staged_files = Publisher(staged_repo, stage / "site").publish()
            destinations = {month_path: staged_path.read_bytes()}
            destinations.update(
                {
                    self.publisher.out_dir / p.relative_to(stage / "site"): p.read_bytes()
                    for p in staged_files
                }
            )
            before = {p: p.read_bytes() if p.exists() else None for p in destinations}
            try:
                for path, contents in destinations.items():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(contents)
            except Exception:
                for path, contents in before.items():
                    if contents is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_bytes(contents)
                raise
        return CommitResult(
            month=preview.month,
            season=preview.season,
            month_path=month_path,
            published=tuple(p for p in destinations if p != month_path),
        )
