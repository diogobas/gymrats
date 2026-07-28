"""The season table: one column per month holding the final position.

Absence scores last place plus one, per month, applied retroactively.
"""

from __future__ import annotations

from gymrats.core import (
    Modality,
    MonthResult,
    Standing,
    absentee_score,
    build_season,
    tally_month,
)

from conftest import make_tables


def month(month_key: str, order: list[str]) -> MonthResult:
    """A minimal MonthResult: names in finishing order, positions 1..n."""
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
            for position, name in enumerate(order, start=1)
        ),
    )


def test_column_holds_the_final_position_not_the_point_total():
    january = month("2026-01", ["A", "B", "C"])

    season = build_season(2026, [january])
    rows = {row.name: row for row in season.rows}

    assert rows["A"].by_month == {"2026-01": 1}
    assert rows["C"].by_month == {"2026-01": 3}


def test_absentee_scores_last_place_plus_one():
    january = month("2026-01", ["A", "B", "C"])
    assert absentee_score(january) == 4


def test_someone_who_joined_later_is_carried_back_to_every_earlier_month():
    january = month("2026-01", ["A", "B", "C"])  # last place is 3 -> absent = 4
    february = month("2026-02", ["A", "B", "C", "D"])

    season = build_season(2026, [january, february])
    rows = {row.name: row for row in season.rows}

    assert rows["D"].by_month == {"2026-01": 4, "2026-02": 4}
    assert rows["D"].imputed_months == ("2026-01",)
    assert rows["D"].total == 8
    assert rows["A"].total == 2
    assert [row.name for row in season.rows] == ["A", "B", "C", "D"]


def test_absentee_score_is_computed_per_month():
    # Different field sizes -> different absentee scores in the same season.
    january = month("2026-01", ["A", "B", "C"])  # absent = 4
    february = month("2026-02", ["A", "B", "C", "D", "E", "F"])  # absent = 7

    season = build_season(2026, [january, february])
    rows = {row.name: row for row in season.rows}

    assert rows["D"].by_month == {"2026-01": 4, "2026-02": 4}
    assert rows["A"].by_month == {"2026-01": 1, "2026-02": 1}

    march = month("2026-03", ["A"])
    season = build_season(2026, [january, february, march])
    rows = {row.name: row for row in season.rows}
    # F did not compete in January (absent = 4) nor March (absent = 2).
    assert rows["F"].by_month == {"2026-01": 4, "2026-02": 6, "2026-03": 2}


def test_lowest_total_leads():
    january = month("2026-01", ["A", "B"])
    february = month("2026-02", ["B", "A"])
    march = month("2026-03", ["B", "A"])

    season = build_season(2026, [january, february, march])

    assert [(row.name, row.total) for row in season.rows] == [("B", 4), ("A", 5)]


def test_season_tie_is_broken_by_distance_in_the_year():
    january = month("2026-01", ["A", "B"])
    february = month("2026-02", ["B", "A"])  # both on 3 points

    year_tables = make_tables(
        distance_year=[("A", 900.0), ("B", 1026.13)],
        duration_year=[("A", 79210), ("B", 1000)],
    )

    season = build_season(2026, [january, february], year_tables)

    assert [row.name for row in season.rows] == ["B", "A"]
    assert season.rows[0].tiebreak.resolved_by is Modality.DISTANCE


def test_season_tie_falls_through_to_duration_in_the_year():
    january = month("2026-01", ["A", "B"])
    february = month("2026-02", ["B", "A"])

    year_tables = make_tables(
        distance_year=[("A", 1000.0), ("B", 1000.0)],
        duration_year=[("A", 5000), ("B", 9000)],
    )

    season = build_season(2026, [january, february], year_tables)

    assert [row.name for row in season.rows] == ["B", "A"]
    assert season.rows[0].tiebreak.resolved_by is Modality.DURATION


def test_unbreakable_season_tie_is_reported():
    january = month("2026-01", ["A", "B"])
    february = month("2026-02", ["B", "A"])

    year_tables = make_tables(
        distance_year=[("A", 1000.0), ("B", 1000.0)],
        duration_year=[("A", 5000), ("B", 5000)],
    )

    season = build_season(2026, [january, february], year_tables)

    assert season.unresolved_ties == (("A", "B"),)
    assert {row.position for row in season.rows} == {1}


def test_excluded_for_zero_hustle_counts_as_an_absence(june_tables, participants):
    """Eduardo sat June out with 0 hustle. In July he competes and is carried back."""
    june = tally_month("2026-06", june_tables, participants)
    july = MonthResult(
        month="2026-07",
        standings=(
            Standing(
                position=1,
                name="Eduardo",
                total=3,
                positions={},
                values={},
                calories_adjusted=0.0,
                calorie_bonus_applied=False,
            ),
        ),
    )

    season = build_season(2026, [june, july])
    rows = {row.name: row for row in season.rows}

    # June ranked 10 people, so the absentee column is 11.
    assert rows["Eduardo"].by_month["2026-06"] == 11
    assert rows["Eduardo"].imputed_months == ("2026-06",)


def test_june_alone_gives_william_ten_points(june_tables, participants):
    """The admin's own check: William finished 10th in June, so he carries 10."""
    june = tally_month("2026-06", june_tables, participants)

    season = build_season(2026, [june])
    rows = {row.name: row for row in season.rows}

    assert rows["William"].by_month == {"2026-06": 10}
    assert rows["William"].total == 10
    assert rows["Arthur"].total == 1
    # Nobody who never competed shows up in the season table.
    assert "Eduardo" not in rows
