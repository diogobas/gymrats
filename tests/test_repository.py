"""The live data under data/, read through the repository.

The fixtures are frozen regression data; data/ is what the admin actually
edits. These tests keep the two from drifting apart silently, and check that
the report runs end to end against real files.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from gymrats.core import build_season, tally_month
from gymrats.report import main as report_main
from gymrats.storage.repository import Repository

DATA = Path(__file__).resolve().parents[1] / "data"

JUNE_ORDER = [
    "Arthur",
    "Andressa",
    "Isadora",
    "Diogo",
    "Bruna",
    "Lorrana",
    "Túlio",
    "Lorena",
    "Laíssa",
    "William",
]
SEASON_ORDER = [
    "Isadora",
    "Diogo",
    "Arthur",
    "Bruna",
    "Andressa",
    "Thamyres",
    "Lorena",
    "Túlio",
    "Laíssa",
    "Nathane",
    "João",
    "William",
    "Lorrana",
    "Paula",
    "Ricardo",
]
SEASON_TOTALS = [15, 16, 16, 24, 34, 49, 50, 51, 52, 57, 59, 65, 66, 69, 76]


@pytest.fixture(scope="module")
def repo():
    return Repository(DATA)


def test_june_is_tallied_from_the_live_data(repo):
    result = tally_month("2026-06", repo.tables("2026-06"), repo.participants())
    assert [row.name for row in result.standings] == JUNE_ORDER


def test_history_and_june_reproduce_the_season_sheet(repo):
    june = tally_month("2026-06", repo.tables("2026-06"), repo.participants())
    season = build_season(
        2026, [*repo.history_results(2026), june], repo.tables("2026-06")
    )

    assert [row.name for row in season.rows] == SEASON_ORDER
    assert [row.total for row in season.rows] == SEASON_TOTALS
    assert season.unresolved_ties == ()


def test_history_stops_where_the_tallied_months_begin(repo):
    """A month must not be both hand-recorded history and a real tally."""
    assert not set(repo.history(2026)) & set(repo.months())


def test_every_name_in_the_data_is_a_registered_participant(repo):
    known = {person.name for person in repo.participants()}

    for month in repo.months():
        for entries in repo.tables(month).data.values():
            unknown = {entry.name for entry in entries} - known
            assert not unknown, f"{month}: {sorted(unknown)}"

    for month, order in repo.history(2026).items():
        assert not set(order) - known, month


def test_the_report_runs(capsys, repo):
    assert report_main(["--data", str(DATA)]) == 0

    out = capsys.readouterr().out
    assert "CLASSIFICAÇÃO — 2026-06" in out
    assert "PONTOS CORRIDOS — 2026" in out
    # The tiebreak explanation is printed once per tie, not once per person.
    assert out.count("Arthur x Andressa") == 1
    assert out.count("Diogo x Arthur") == 1
