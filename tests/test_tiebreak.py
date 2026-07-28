"""Rule 5: distance, then duration, then declare the tie."""

from __future__ import annotations

from gymrats.core import Modality, tally_month

from conftest import make_tables


def _two_way_tie(distance, duration):
    """Two people guaranteed to tie on 4 points, separated only by the cascade."""
    return make_tables(
        hustle=[("A", 300), ("B", 300)],
        active_days=[("A", 20), ("B", 20)],
        calories=[("A", 1000), ("B", 1000)],
        distance=distance,
        duration=duration,
    )


def test_distance_breaks_the_tie_first():
    tables = _two_way_tie(
        distance=[("A", 90), ("B", 100)],
        duration=[("A", 5000), ("B", 100)],  # A has far more time and still loses
    )
    result = tally_month("2026-06", tables, [])

    assert [row.name for row in result.standings] == ["B", "A"]
    assert result.standings[0].tiebreak.resolved_by is Modality.DISTANCE
    assert result.standings[0].tiebreak.tied_with == ("A",)
    assert result.unresolved_ties == ()


def test_duration_breaks_it_only_when_distance_is_level():
    tables = _two_way_tie(
        distance=[("A", 100), ("B", 100)],
        duration=[("A", 900), ("B", 1200)],
    )
    result = tally_month("2026-06", tables, [])

    assert [row.name for row in result.standings] == ["B", "A"]
    assert result.standings[0].tiebreak.resolved_by is Modality.DURATION


def test_an_unbreakable_tie_is_reported_not_decided():
    tables = _two_way_tie(
        distance=[("A", 100), ("B", 100)],
        duration=[("A", 900), ("B", 900)],
    )
    result = tally_month("2026-06", tables, [])

    assert result.unresolved_ties == (("A", "B"),)
    # Both hold the same position -- no winner was invented.
    assert {row.position for row in result.standings} == {1}
    assert all(row.tiebreak.resolved_by is None for row in result.standings)


def test_positions_skip_after_an_unresolved_tie():
    tables = make_tables(
        hustle=[("A", 300), ("B", 300), ("C", 100)],
        active_days=[("A", 20), ("B", 20), ("C", 10)],
        calories=[("A", 1000), ("B", 1000), ("C", 500)],
        distance=[("A", 100), ("B", 100), ("C", 50)],
        duration=[("A", 900), ("B", 900), ("C", 400)],
    )
    result = tally_month("2026-06", tables, [])

    positions = {row.name: row.position for row in result.standings}
    assert positions == {"A": 1, "B": 1, "C": 3}
    # Absentees are scored off last place, which is 3 here, not the head count.
    assert result.last_position == 3


def test_missing_from_the_distance_table_loses_the_tiebreak():
    tables = make_tables(
        hustle=[("A", 300), ("B", 300)],
        active_days=[("A", 20), ("B", 20)],
        calories=[("A", 1000), ("B", 1000)],
        distance=[("B", 10)],  # A is not on the leaderboard at all
        duration=[("A", 9999), ("B", 1)],
    )
    result = tally_month("2026-06", tables, [])

    assert [row.name for row in result.standings] == ["B", "A"]


def test_three_way_tie_splits_partially():
    # B and C separate from A on distance, then tie there and split on duration.
    tables = make_tables(
        hustle=[("A", 300), ("B", 300), ("C", 300)],
        active_days=[("A", 20), ("B", 20), ("C", 20)],
        calories=[("A", 1000), ("B", 1000), ("C", 1000)],
        distance=[("A", 50), ("B", 100), ("C", 100)],
        duration=[("A", 900), ("B", 200), ("C", 800)],
    )
    result = tally_month("2026-06", tables, [])

    assert [row.name for row in result.standings] == ["C", "B", "A"]
    assert result.standings[0].tiebreak.resolved_by is Modality.DURATION
    assert result.standings[2].tiebreak.resolved_by is Modality.DISTANCE
    assert result.unresolved_ties == ()
