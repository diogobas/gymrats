"""The closed June 2026 tally, end to end, against the admin's own screenshots.

Expected result, from the admin's June sheet:

    #   name       pts   hustle  days  cal
    1   Arthur      4      2      1     1
    2   Andressa    4      1      1     2
    3   Isadora    10      3      3     4
    4   Diogo      13      4      6     3
    5   Bruna      16      5      4     7
    6   Lorrana    16      6      5     5
    7   Túlio      20      7      7     6
    8   Lorena     24      8      8     8
    9   Laíssa     27      9      9     9
    10  William    30     10     10    10

Two ties on the total -- Arthur/Andressa and Bruna/Lorrana -- so the case
exercises the whole cascade. The distance and duration values behind those two
tiebreaks are still placeholders; see the fixture.
"""

from __future__ import annotations

import pytest

from gymrats.core import Modality, Period, competition_rank, tally_month
from gymrats.storage.schema import participants_from_dict, tables_from_dict

from conftest import load_fixture

# name -> (hustle, active_days, calories, total), straight off the sheet.
EXPECTED = {
    "Arthur": (2, 1, 1, 4),
    "Andressa": (1, 1, 2, 4),
    "Isadora": (3, 3, 4, 10),
    "Diogo": (4, 6, 3, 13),
    "Bruna": (5, 4, 7, 16),
    "Lorrana": (6, 5, 5, 16),
    "Túlio": (7, 7, 6, 20),
    "Lorena": (8, 8, 8, 24),
    "Laíssa": (9, 9, 9, 27),
    "William": (10, 10, 10, 30),
}
FINISHING_ORDER = list(EXPECTED)


def test_june_reproduces_the_closed_tally(june_tables, participants):
    result = tally_month("2026-06", june_tables, participants)

    assert [row.name for row in result.standings] == FINISHING_ORDER
    assert [row.total for row in result.standings] == [
        EXPECTED[name][3] for name in FINISHING_ORDER
    ]
    assert [row.position for row in result.standings] == list(range(1, 11))
    assert result.ranked_count == 10


@pytest.mark.parametrize("name", FINISHING_ORDER)
def test_june_per_modality_positions_match_the_sheet(june_tables, participants, name):
    result = tally_month("2026-06", june_tables, participants)
    row = next(r for r in result.standings if r.name == name)
    hustle, active_days, calories, total = EXPECTED[name]

    assert row.positions[Modality.HUSTLE] == hustle
    assert row.positions[Modality.ACTIVE_DAYS] == active_days
    assert row.positions[Modality.CALORIES] == calories
    assert row.total == total


def test_june_has_exactly_one_tie_inside_a_scoring_table(june_tables, participants):
    """Arthur and Andressa both logged 26 active days.

    With 10 ranked people the three position columns sum to 3 * (1+..+10) =
    165 when no modality has a tie; each two-way tie inside a column takes one
    off. June's totals sum to 164, and active_days is where the tie is.
    """
    result = tally_month("2026-06", june_tables, participants)

    assert sum(row.total for row in result.standings) == 164

    active = [row.positions[Modality.ACTIVE_DAYS] for row in result.standings]
    assert sorted(active) == [1, 1, 3, 4, 5, 6, 7, 8, 9, 10]

    for modality in (Modality.HUSTLE, Modality.CALORIES):
        column = sorted(row.positions[modality] for row in result.standings)
        assert column == list(range(1, 11))


def test_june_excludes_everyone_on_zero_hustle(june_tables, participants):
    result = tally_month("2026-06", june_tables, participants)

    excluded = {item.name for item in result.excluded}
    assert excluded == {"Paula", "Rayza", "Ricardo", "Nathane"}
    assert all(item.reason.value == "zero_hustle" for item in result.excluded)
    assert not excluded & {row.name for row in result.standings}


def test_june_calorie_bonus_reorders_the_table(june_tables, participants):
    """Raw order and bonused order differ for six of the ten places."""
    result = tally_month("2026-06", june_tables, participants)
    by_name = {row.name: row for row in result.standings}

    raw_order = competition_rank(
        [(e.name, e.value) for e in june_tables.get(Modality.CALORIES, Period.MONTH)]
    )
    assert raw_order["Andressa"] == 3
    assert by_name["Andressa"].positions[Modality.CALORIES] == 2
    assert by_name["Andressa"].calories_adjusted == 12711.6

    # Túlio logged more raw calories than Lorrana and still ends up behind her.
    assert raw_order["Túlio"] < raw_order["Lorrana"]
    assert (
        by_name["Túlio"].positions[Modality.CALORIES]
        > by_name["Lorrana"].positions[Modality.CALORIES]
    )

    bonused = {row.name for row in result.standings if row.calorie_bonus_applied}
    assert bonused == {"Andressa", "Isadora", "Bruna", "Lorrana", "Lorena", "Laíssa"}


def test_june_reported_positions_agree_with_the_computed_order(june_tables):
    """The app's own numbering is the OCR cross-check.

    Compared against the RAW order, including for calories -- GymRats knows
    nothing about the +20% bonus, so the number it prints on screen ranks the
    unbonused figure.
    """
    for modality in Modality:
        entries = [
            entry
            for entry in june_tables.get(modality, Period.MONTH)
            if entry.reported_position is not None
        ]
        if not entries:
            continue
        computed = competition_rank([(e.name, e.value) for e in entries])
        for entry in entries:
            assert entry.reported_position == computed[entry.name], (
                f"{modality.value}: {entry.name}"
            )


def test_june_ties_go_through_the_cascade(june_tables, participants):
    """Both ties are settled, and neither is left for the admin to decide."""
    result = tally_month("2026-06", june_tables, participants)
    by_name = {row.name: row for row in result.standings}

    assert by_name["Arthur"].tiebreak.tied_with == ("Andressa",)
    assert by_name["Bruna"].tiebreak.tied_with == ("Lorrana",)
    assert by_name["Arthur"].tiebreak.resolved_by is not None
    assert by_name["Bruna"].tiebreak.resolved_by is not None
    assert result.unresolved_ties == ()


def test_june_tiebreak_criterion_is_still_unverified(june_input):
    """Guard: activates itself when the real distance and duration arrive.

    Which criterion decided Arthur over Andressa and Bruna over Lorrana is a
    claim about real numbers this fixture does not have yet. Drop the
    "_placeholder" flags when the prints land, and this test starts demanding
    the criterion be pinned down.
    """
    placeholders = sorted(
        modality
        for modality, block in june_input["tables"].items()
        if block.get("_placeholder")
    )
    if placeholders:
        pytest.skip(f"still placeholder: {placeholders}")

    result = tally_month("2026-06", tables_from_dict(june_input), participants_from_dict(
        load_fixture("participants.json")
    ))
    by_name = {row.name: row for row in result.standings}
    assert by_name["Arthur"].tiebreak.resolved_by is Modality.DISTANCE
    assert by_name["Bruna"].tiebreak.resolved_by is Modality.DISTANCE
