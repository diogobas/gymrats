"""The closed June 2026 tally, end to end.

The expected result is the real one, as reported by the admin:

    Arthur 4, Andressa 4, Isadora 10, Diogo 13, Bruna 16, Lorrana 16,
    Túlio 20, Lorena 24, Laíssa 27, William 30

Two ties on the total (Arthur/Andressa and Bruna/Lorrana) make this the case
that exercises the whole cascade. See the note inside the fixture for how the
raw values were reconstructed from that result.
"""

from __future__ import annotations

from gymrats.core import Modality, tally_month

EXPECTED = [
    ("Arthur", 4),
    ("Andressa", 4),
    ("Isadora", 10),
    ("Diogo", 13),
    ("Bruna", 16),
    ("Lorrana", 16),
    ("Túlio", 20),
    ("Lorena", 24),
    ("Laíssa", 27),
    ("William", 30),
]


def test_june_reproduces_the_closed_tally(june_tables, participants):
    result = tally_month("2026-06", june_tables, participants)

    assert [(row.name, row.total) for row in result.standings] == EXPECTED
    assert [row.position for row in result.standings] == list(range(1, 11))
    assert result.ranked_count == 10


def test_june_position_columns_are_valid_rankings(june_tables, participants):
    """Every scoring column must be a competition ranking over the 10 ranked."""
    result = tally_month("2026-06", june_tables, participants)

    for modality in (Modality.HUSTLE, Modality.ACTIVE_DAYS, Modality.CALORIES):
        column = sorted(row.positions[modality] for row in result.standings)
        assert len(column) == 10
        assert column[0] == 1
        # Competition ranking: a position is either new or repeats the one
        # before it, and repeats consume the numbers they skip.
        for index, position in enumerate(column, start=1):
            assert position <= index

    # The arithmetic that pins the fixture: 3 * (1+..+10) = 165 with no ties,
    # and one two-way tie inside a column takes it to 164.
    assert sum(row.total for row in result.standings) == 164


def test_june_excludes_the_zero_hustle_entry(june_tables, participants):
    result = tally_month("2026-06", june_tables, participants)

    assert [item.name for item in result.excluded] == ["Eduardo"]
    assert "Eduardo" not in {row.name for row in result.standings}


def test_june_ties_are_broken_by_distance(june_tables, participants):
    result = tally_month("2026-06", june_tables, participants)
    by_name = {row.name: row for row in result.standings}

    arthur = by_name["Arthur"]
    assert arthur.tiebreak is not None
    assert arthur.tiebreak.tied_with == ("Andressa",)
    assert arthur.tiebreak.resolved_by is Modality.DISTANCE

    # Lorrana logged MORE duration than Bruna and still finished behind her --
    # distance comes first and the cascade stops there.
    bruna, lorrana = by_name["Bruna"], by_name["Lorrana"]
    assert bruna.tiebreak.resolved_by is Modality.DISTANCE
    assert bruna.values[Modality.DISTANCE] > lorrana.values[Modality.DISTANCE]
    assert bruna.values[Modality.DURATION] < lorrana.values[Modality.DURATION]

    assert result.unresolved_ties == ()


def test_june_calorie_bonus_moved_andressa_to_first(june_tables, participants):
    result = tally_month("2026-06", june_tables, participants)
    by_name = {row.name: row for row in result.standings}

    andressa, arthur = by_name["Andressa"], by_name["Arthur"]

    assert andressa.calorie_bonus_applied is True
    assert arthur.calorie_bonus_applied is False
    # Arthur logged more raw calories...
    assert arthur.values[Modality.CALORIES] > andressa.values[Modality.CALORIES]
    # ...but the +20% puts Andressa on top of that table.
    assert andressa.calories_adjusted == 17926.8
    assert andressa.positions[Modality.CALORIES] == 1
    assert arthur.positions[Modality.CALORIES] == 2


def test_june_reported_positions_agree_with_the_computed_order(june_tables):
    """The app's own numbering is the OCR cross-check.

    Compared against the RAW order for every modality -- including calories,
    because GymRats knows nothing about the +20% bonus.
    """
    from gymrats.core import Period, competition_rank

    for modality in Modality:
        entries = june_tables.get(modality, Period.MONTH)
        computed = competition_rank([(e.name, e.value) for e in entries])
        for entry in entries:
            assert entry.reported_position == computed[entry.name], (
                f"{modality.value}: {entry.name}"
            )
