"""The 2026 season table through June, against the admin's "Pontos Corridos".

Real data end to end. Six months, fifteen people, field sizes ranging from 10
to 15 -- so the absentee rule (last place + 1, per month, applied
retroactively) is exercised on five different values: 14, 13, 14, 12, 11.

The code is never told the absentee score. It is given only who was ranked in
each month, in order, and has to derive the rest.
"""

from __future__ import annotations

import pytest

from gymrats.core import (
    Modality,
    MonthResult,
    Period,
    Standing,
    absentee_score,
    build_season,
)
from gymrats.storage.schema import tables_from_dict

from conftest import load_fixture

SEASON = load_fixture("season-2026.json")
MONTHS = list(SEASON["ranked"])
EXPECTED = SEASON["expected"]


def month_result(month_key: str) -> MonthResult:
    """Only the finishing order -- absences are for build_season to work out."""
    return MonthResult(
        month=month_key,
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
            for position, name in enumerate(SEASON["ranked"][month_key], start=1)
        ),
    )


@pytest.fixture(scope="module")
def year_tables():
    """The "Este ano" snapshot from the most recent tallied month, June."""
    return tables_from_dict(load_fixture("2026-06.json"))


@pytest.fixture(scope="module")
def season(year_tables):
    return build_season(2026, [month_result(key) for key in MONTHS], year_tables)


def test_every_month_is_present(season):
    assert list(season.months) == MONTHS


@pytest.mark.parametrize("month_key", MONTHS)
def test_absentee_score_is_last_place_plus_one(month_key):
    expected = SEASON["absentee_score"][month_key]
    assert absentee_score(month_result(month_key)) == expected


@pytest.mark.parametrize("row", EXPECTED, ids=lambda row: row["name"])
def test_monthly_columns_match_the_sheet(season, row):
    actual = {r.name: r for r in season.rows}[row["name"]]
    assert [actual.by_month[key] for key in MONTHS] == row["by_month"]


@pytest.mark.parametrize("row", EXPECTED, ids=lambda row: row["name"])
def test_totals_match_the_sheet(season, row):
    actual = {r.name: r for r in season.rows}[row["name"]]
    assert actual.total == row["total"]


def test_everyone_on_the_sheet_is_accounted_for(season):
    assert {r.name for r in season.rows} == {row["name"] for row in EXPECTED}
    # Rayza is in the app but never scored in 2026, so she is not on the table.
    assert "Rayza" not in {r.name for r in season.rows}


def test_the_whole_order_matches_the_sheet(season):
    assert [r.name for r in season.rows] == [row["name"] for row in EXPECTED]
    assert [r.position for r in season.rows] == [row["position"] for row in EXPECTED]


def test_the_diogo_arthur_tie_is_settled_by_distance_in_the_year(season):
    """Both on 16. The sheet puts Diogo 2nd, and the year distance says why.

    1,026.13 km against Arthur's 893.06 -- so the sheet's ordering was not
    arbitrary and the published result can justify itself.
    """
    rows = {r.name: r for r in season.rows}
    diogo, arthur = rows["Diogo"], rows["Arthur"]

    assert diogo.total == arthur.total == 16
    assert (diogo.position, arthur.position) == (2, 3)
    assert diogo.tiebreak.resolved_by is Modality.DISTANCE
    assert diogo.tiebreak.tied_with == ("Arthur",)
    assert diogo.tiebreak.comparison == {"Diogo": 1026.13, "Arthur": 893.06}
    assert season.unresolved_ties == ()


def test_the_season_tiebreak_ignores_the_monthly_numbers(season, year_tables):
    """Arthur out-ran Diogo in June and it does not help him in the season.

    The annual cascade reads the year snapshot, not a sum of months.
    """
    june_distance = {
        e.name: e.value for e in year_tables.get(Modality.DISTANCE, Period.MONTH)
    }
    assert june_distance["Diogo"] > june_distance["Arthur"]

    year_duration = {
        e.name: e.value for e in year_tables.get(Modality.DURATION, Period.YEAR)
    }
    # Arthur leads the year on duration -- the second criterion, never reached.
    assert year_duration["Arthur"] > year_duration["Diogo"]

    rows = {r.name: r for r in season.rows}
    assert rows["Diogo"].position == 2


def test_someone_who_joined_late_is_carried_back():
    """Nathane did not compete in January; the sheet gives her 14 for it."""
    season = build_season(2026, [month_result(key) for key in MONTHS])
    nathane = {r.name: r for r in season.rows}["Nathane"]

    assert nathane.by_month["2026-01"] == 14
    assert "2026-01" in nathane.imputed_months
    assert "2026-02" not in nathane.imputed_months
    assert nathane.by_month["2026-02"] == 15


def test_a_full_month_imputes_nobody():
    """February had all fifteen competing."""
    season = build_season(2026, [month_result("2026-02")])

    assert all(row.imputed_months == () for row in season.rows)
    assert len(season.rows) == 15
