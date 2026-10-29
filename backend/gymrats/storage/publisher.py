"""Writing the JSON the static site reads.

The only component that writes anything. It recomputes every tally from
``data/`` -- the same path ``report`` walks -- and drops the result under
``frontend/public/data/``, which Vite copies into ``dist/`` verbatim.

Three kinds of file come out:

* ``months/YYYY-MM.json``  -- one tallied month, exactly ``month_result_to_dict``
* ``season/YYYY.json``     -- the season table, exactly ``season_result_to_dict``
* ``index.json``           -- the manifest the site loads first

Months that only exist in ``data/history/`` (tallied by hand before this
system) get no file of their own: the finishing order the site shows for them
comes from ``by_month`` in the season document. The manifest marks them
``detail: false`` so the site knows which of the two it is dealing with before
fetching anything.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..core.models import MonthResult, SeasonResult, Tables
from ..core.scoring import tally_month
from ..core.season import build_season
from .repository import Repository
from .schema import SCHEMA_VERSION, month_result_to_dict, season_result_to_dict

__all__ = ["DEFAULT_OUTPUT", "Publisher"]

#: Vite copies everything under ``public/`` into the build as-is.
DEFAULT_OUTPUT = Path("frontend/public/data")


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write(path: Path, document: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Indented and with the accents intact: these files are committed, so a
    # diff between two tallies has to be readable.
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


class Publisher:
    """Turns ``data/`` into the site's ``data/`` directory."""

    def __init__(
        self,
        repo: Repository,
        out_dir: Path | str = DEFAULT_OUTPUT,
    ) -> None:
        self.repo = repo
        self.out_dir = Path(out_dir)

    # -- the tallies -------------------------------------------------------

    def month(self, month: str) -> MonthResult:
        return tally_month(
            month, self.repo.public_tables(month), self.repo.participants()
        )

    def season(self, year: int, *, include_provisional: bool = True) -> SeasonResult:
        """The season table for ``year``, history and tallied months together.

        The tiebreak reads the "Este ano" leaderboards from the most recent
        tallied month -- what the app is showing today, not a sum of months.
        """
        months = (
            tuple(m for m in self.repo.published_months() if m.startswith(f"{year}-"))
            if include_provisional
            else self.repo.months_of(year)
        )
        tallied = [self.month(month) for month in months]
        year_tables = self.repo.public_tables(months[-1]) if months else Tables.build({})
        results = [
            *[r for r in self.repo.history_results(year) if r.month not in months],
            *tallied,
        ]
        return build_season(year, results, year_tables, **self.repo.season_options(year))

    # -- the files ---------------------------------------------------------

    def index(self, generated_at: str) -> dict:
        years = self.repo.years()
        tallied = set(self.repo.published_months())

        months: list[dict] = []
        for year in years:
            known = tallied | set(self.repo.history(year))
            for month in sorted(m for m in known if m.startswith(f"{year}-")):
                months.append(
                    {
                        "month": month,
                        "year": year,
                        # False means "history": no leaderboards were kept, so
                        # there is no months/<month>.json to fetch.
                        "detail": month in tallied,
                        **self.repo.provisional_info(month),
                    }
                )

        latest = max(tallied) if tallied else (months[-1]["month"] if months else None)
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "latest_month": latest,
            "latest_completed_month": max(self.repo.months(), default=None),
            "latest_year": years[-1] if years else None,
            "years": list(years),
            "months": months,
        }

    def season_info(self, year: int) -> dict:
        months = [m for m in self.repo.published_months() if m.startswith(f"{year}-")]
        info = self.repo.provisional_info(months[-1]) if months else {}
        known = set(months) | set(self.repo.history(year))
        if known:
            missing = [
                f"{year}-{number:02d}"
                for number in range(1, int(max(known)[-2:]))
                if f"{year}-{number:02d}" not in known
            ]
            if missing:
                info["missing_months"] = missing
        return info

    def publish(self, *, generated_at: str | None = None) -> tuple[Path, ...]:
        """Write every file and return the paths, in the order written.

        ``generated_at`` is injectable so a test can assert on bytes.
        """
        stamp = generated_at or _timestamp()
        written = [
            _write(
                self.out_dir / "months" / f"{month}.json",
                {
                    **month_result_to_dict(self.month(month), stamp),
                    **self.repo.provisional_info(month),
                },
            )
            for month in self.repo.published_months()
        ]
        written += [
            _write(
                self.out_dir / "season" / f"{year}.json",
                {
                    **season_result_to_dict(self.season(year), stamp),
                    **self.season_info(year),
                },
            )
            for year in self.repo.years()
        ]
        written.append(_write(self.out_dir / "index.json", self.index(stamp)))
        return tuple(written)
