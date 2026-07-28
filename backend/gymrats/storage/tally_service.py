"""Tallying a month that has not been written yet, and then writing it.

The preview exists so the admin sees the standings *before* anything touches
``data/``: the same numbers, computed the same way, with the month that is
still a draft slotted into the season alongside the ones already on disk.

Committing is the only path that writes, and it does three things in order:
store the reviewed leaderboards, republish the site's JSON, and hand back the
result. If the first step fails, nothing was published.
"""

from __future__ import annotations

from dataclasses import dataclass
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

    def preview(self, month: str, tables: Tables) -> TallyPreview:
        """What committing would produce, without producing it."""
        participants = self.repo.participants()
        result = tally_month(month, tables, participants)
        year = int(month[:4])

        # Every other month of the season comes off disk; this one comes from
        # the draft. A re-tally of a month already committed replaces it
        # rather than appearing twice.
        others = [
            tally_month(other, self.repo.tables(other), participants)
            for other in self.repo.months_of(year)
            if other != month
        ]
        results = [*self.repo.history_results(year), *others, result]

        latest = max(month, *self.repo.months_of(year))
        year_tables = tables if latest == month else self.repo.tables(latest)

        return TallyPreview(month=result, season=build_season(year, results, year_tables))

    def commit(self, month: str, tables: Tables) -> CommitResult:
        month_path = self.repo.write_tables(month, tables)
        published = self.publisher.publish()
        preview = self.preview(month, tables)
        return CommitResult(
            month=preview.month,
            season=preview.season,
            month_path=month_path,
            published=published,
        )
