"""The 2026 season table through June, against the admin's "Pontos Corridos".

Real data end to end. Six months, fifteen people, field sizes ranging from 10
to 15 -- so the absentee rule (last place + 1, per month, applied
retroactively) is exercised on five different values: 14, 13, 14, 12, 11.

The code is never told the absentee score. It is given only who was ranked in
each month, in order, and has to derive the rest.
"""

from __future__ import annotations

import pytest

from gymrats.core import MonthResult, Standing, absentee_score, build_season

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
def season():
    return build_season(2026, [month_result(key) for key in MONTHS])


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


def test_the_order_matches_the_sheet_apart_from_the_open_tie(season):
    """Diogo and Arthur are both on 16 -- see the fixture's open question."""
    ordered = [r.name for r in season.rows]
    expected = [row["name"] for row in EXPECTED]

    assert ordered[0] == expected[0] == "Isadora"
    assert set(ordered[1:3]) == {"Diogo", "Arthur"}
    assert ordered[3:] == expected[3:]


def test_the_diogo_arthur_tie_is_reported_not_invented(season):
    """Without the year figures the cascade has nothing to go on.

    It must say so rather than pick one, which is exactly rule 5c. Once the
    year distance arrives this becomes a resolved tie and the assertion below
    flips -- that is the point.
    """
    # Order inside an unresolved block carries no meaning -- that is the point.
    assert len(season.unresolved_ties) == 1
    assert set(season.unresolved_ties[0]) == {"Diogo", "Arthur"}

    tied = [r for r in season.rows if r.name in {"Diogo", "Arthur"}]
    assert {r.position for r in tied} == {2}
    assert all(r.tiebreak.resolved_by is None for r in tied)

    # Competition ranking: the pair holds 2, so the next person takes 4.
    bruna = next(r for r in season.rows if r.name == "Bruna")
    assert bruna.position == 4


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
