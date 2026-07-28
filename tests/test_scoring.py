"""Rules 1 to 4: bonus, exclusion, competition ranking, sum of positions."""

from __future__ import annotations

from decimal import Decimal

from conftest import make_tables
from gymrats.core import (
    Modality,
    Participant,
    adjusted_calories,
    competition_rank,
    tally_month,
)

# -- rule 3: competition ranking -------------------------------------------


def test_ties_share_the_position_and_the_next_one_skips():
    positions = competition_rank([("a", 10), ("b", 10), ("c", 5)])
    assert positions == {"a": 1, "b": 1, "c": 3}


def test_three_way_tie_skips_two_positions():
    positions = competition_rank([("a", 10), ("b", 10), ("c", 10), ("d", 5)])
    assert positions == {"a": 1, "b": 1, "c": 1, "d": 4}


def test_season_ranking_inverts_the_comparison():
    positions = competition_rank(
        [("a", 23), ("b", 19), ("c", 23)], higher_is_better=False
    )
    assert positions == {"b": 1, "a": 2, "c": 2}


def test_bonus_arithmetic_is_exact_not_binary_float():
    # 3 * 1.2 is 3.5999999999999996 in binary floating point.
    assert 3 * 1.2 != 3.6
    assert adjusted_calories(3, bonus=True) == Decimal("3.6")


def test_values_that_are_mathematically_equal_tie():
    # A's bonus lands exactly on B's raw figure. Computed in float, the drift
    # would hand one of them a position they did not earn.
    positions = competition_rank(
        [
            ("a", adjusted_calories(3, bonus=True)),
            ("b", adjusted_calories(3.6, bonus=False)),
        ]
    )
    assert positions == {"a": 1, "b": 1}


# -- rule 1: calorie bonus --------------------------------------------------


def test_bonus_is_exactly_twenty_percent():
    assert adjusted_calories(14939, bonus=True) == Decimal("17926.8")
    assert adjusted_calories(14939, bonus=False) == Decimal(14939)


def test_bonus_is_applied_before_sorting_and_can_flip_the_order():
    tables = make_tables(
        hustle=[("Arthur", 300), ("Andressa", 290)],
        active_days=[("Arthur", 20), ("Andressa", 19)],
        calories=[("Arthur", 15980), ("Andressa", 14939)],
        distance=[("Arthur", 100), ("Andressa", 90)],
        duration=[("Arthur", 1000), ("Andressa", 900)],
    )
    people = [
        Participant("Arthur", calorie_bonus=False),
        Participant("Andressa", calorie_bonus=True),
    ]

    result = tally_month("2026-06", tables, people)
    by_name = {row.name: row for row in result.standings}

    # Arthur has more raw calories, Andressa wins the table after the bonus.
    assert by_name["Andressa"].positions[Modality.CALORIES] == 1
    assert by_name["Arthur"].positions[Modality.CALORIES] == 2
    assert by_name["Andressa"].calories_adjusted == 17926.8
    assert by_name["Andressa"].values[Modality.CALORIES] == 14939


def test_bonus_never_touches_distance_or_duration():
    tables = make_tables(
        hustle=[("A", 300), ("B", 300)],
        active_days=[("A", 20), ("B", 20)],
        # A's bonus lands exactly on B's raw figure, so the three scoring
        # tables tie and the cascade has to decide.
        calories=[("A", 1000), ("B", 1200)],
        # A has the bonus but LESS distance; the raw value must decide.
        distance=[("A", 90), ("B", 100)],
        duration=[("A", 900), ("B", 800)],
    )
    people = [Participant("A", calorie_bonus=True), Participant("B")]

    result = tally_month("2026-06", tables, people)

    assert [row.name for row in result.standings] == ["B", "A"]
    assert result.standings[0].tiebreak.resolved_by is Modality.DISTANCE


# -- rule 2: zero hustle ----------------------------------------------------


def test_zero_hustle_is_excluded_and_does_not_consume_a_position():
    tables = make_tables(
        hustle=[("A", 300), ("Zero", 0), ("B", 200)],
        active_days=[("A", 20), ("Zero", 5), ("B", 10)],
        calories=[("A", 1000), ("Zero", 500), ("B", 800)],
        distance=[("A", 90), ("Zero", 10), ("B", 80)],
        duration=[("A", 900), ("Zero", 100), ("B", 800)],
    )

    result = tally_month("2026-06", tables, [])

    assert [row.name for row in result.standings] == ["A", "B"]
    assert [item.name for item in result.excluded] == ["Zero"]
    assert result.excluded[0].reason.value == "zero_hustle"
    # B is second, not third -- the excluded row is out before ranking.
    assert result.standings[1].position == 2
    assert result.standings[1].total == 6


# -- rule 4: sum of the three positions -------------------------------------


def test_monthly_score_is_the_sum_of_the_three_positions():
    tables = make_tables(
        hustle=[("A", 300), ("B", 200), ("C", 100)],
        active_days=[("A", 30), ("B", 20), ("C", 10)],
        calories=[("A", 100), ("B", 200), ("C", 300)],
        distance=[("A", 3), ("B", 2), ("C", 1)],
        duration=[("A", 3), ("B", 2), ("C", 1)],
    )

    result = tally_month("2026-06", tables, [])
    totals = {row.name: row.total for row in result.standings}

    assert totals == {"A": 1 + 1 + 3, "B": 2 + 2 + 2, "C": 3 + 3 + 1}
    assert [row.name for row in result.standings] == ["A", "B", "C"]
    # No ties, so nothing went through the cascade.
    assert all(row.tiebreak is None for row in result.standings)
