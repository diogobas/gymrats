"""The review step: merge the parts, resolve the names, doubt the values.

The rule that matters most here is the cross-check against the app's own
numbering, and specifically that it compares against the RAW order. GymRats
prints those ranks knowing nothing about the +20% calorie bonus.
"""

from __future__ import annotations

import pytest
from gymrats.core import Modality, Participant, Period
from gymrats.ocr import ExtractedRow, Extraction
from gymrats.review import IssueType, assemble, review, to_tables

ROSTER = (
    Participant("Arthur", ("Arthur Pereira",)),
    Participant("Túlio", ("Tulio",)),
    Participant("Lorrana", (), calorie_bonus=True),
    Participant("Andressa", ("Andressa Barcelos Aires Barros",), calorie_bonus=True),
)


def extraction(modality, period, rows, item_id="print.png"):
    return Extraction(
        modality=modality,
        period=period,
        rows=tuple(ExtractedRow(*row) for row in rows),
        item_id=item_id,
    )


def issues_of(draft, kind):
    return [issue for issue in draft.issues if issue.type is kind]


# -- merging the parts of a split leaderboard ------------------------------


def test_two_screenshots_of_one_list_become_one_table():
    """A leaderboard longer than the screen arrives in two parts."""
    top = extraction(
        Modality.HUSTLE,
        Period.MONTH,
        [("Arthur", "356.50 pontos", 1), ("Túlio", "185.17 pontos", 2)],
        item_id="a.png",
    )
    bottom = extraction(
        Modality.HUSTLE,
        Period.MONTH,
        # The overlap is normal: the second screenshot starts where the eye
        # was, not where the first one ended.
        [("Túlio", "185.17 pontos", 2), ("Lorrana", "120.00 pontos", 3)],
        item_id="b.png",
    )

    (table,) = assemble([top, bottom])

    assert [row.name for row in table.rows] == ["Arthur", "Túlio", "Lorrana"]
    assert table.sources == ("a.png", "b.png")


def test_the_same_name_with_two_different_values_is_kept_and_flagged():
    """Merging silently would pick a winner between two readings."""
    parts = [
        extraction(Modality.HUSTLE, Period.MONTH, [("Arthur", "356.50 pontos", 1)]),
        extraction(Modality.HUSTLE, Period.MONTH, [("Arthur", "356.60 pontos", 1)]),
    ]

    draft = review(assemble(parts), ROSTER)

    assert len(draft.tables[0].rows) == 2
    assert [issue.name for issue in issues_of(draft, IssueType.DUPLICATE_NAME)] == [
        "Arthur"
    ]


def test_a_screenshot_with_no_readable_header_is_kept_apart():
    """Guessing which leaderboard it is would be worse than asking."""
    draft = review(
        assemble([extraction(None, None, [("Arthur", "356.50 pontos", 1)])]), ROSTER
    )

    assert draft.tables[0].modality is None
    assert issues_of(draft, IssueType.MISSING_MODALITY)
    assert issues_of(draft, IssueType.MISSING_PERIOD)


def test_a_header_that_gave_up_only_the_period_says_so():
    draft = review(
        assemble([extraction(None, Period.YEAR, [("Arthur", "1 dia ativo", 1)])]), ROSTER
    )

    assert issues_of(draft, IssueType.MISSING_MODALITY)
    assert not issues_of(draft, IssueType.MISSING_PERIOD)


# -- names -----------------------------------------------------------------


def test_an_alias_resolves_and_the_accent_is_forgiven():
    draft = review(
        assemble(
            [
                extraction(
                    Modality.HUSTLE,
                    Period.MONTH,
                    [
                        ("Arthur Pereira", "356.50 pontos", 1),
                        ("Tulio", "185.17 pontos", 2),
                    ],
                )
            ]
        ),
        ROSTER,
    )

    assert [row.resolved_name for row in draft.tables[0].rows] == ["Arthur", "Túlio"]
    assert not issues_of(draft, IssueType.UNKNOWN_NAME)


def test_an_unknown_name_is_never_guessed():
    """`resolve` returns None and the screen asks. It does not pick the
    closest match, because the closest match is a person."""
    draft = review(
        assemble(
            [extraction(Modality.HUSTLE, Period.MONTH, [("Arthurzinho", "10 pontos", 1)])]
        ),
        ROSTER,
    )

    assert draft.tables[0].rows[0].resolved_name is None
    assert [issue.name for issue in issues_of(draft, IssueType.UNKNOWN_NAME)] == [
        "Arthurzinho"
    ]


# -- values ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("modality", "raw", "expected"),
    [
        (Modality.HUSTLE, "339.75 pontos", 339.75),
        (Modality.ACTIVE_DAYS, "24 dias ativo", 24.0),
        (Modality.CALORIES, "14,939 calorias", 14939.0),
        (Modality.DISTANCE, "1,026.13 quilômetros", 1026.13),
        (Modality.DURATION, "221 hr 41 min", 13301.0),
        (Modality.DURATION, "41 min", 41.0),
    ],
)
def test_values_are_read_by_the_domain_not_by_the_engine(modality, raw, expected):
    draft = review(
        assemble([extraction(modality, Period.MONTH, [("Arthur", raw, 1)])]), ROSTER
    )

    assert draft.tables[0].rows[0].value == expected


def test_an_unreadable_value_does_not_become_zero():
    """Zero is a score. "could not read" is not."""
    draft = review(
        assemble(
            [extraction(Modality.HUSTLE, Period.MONTH, [("Arthur", "ilegível", 1)])]
        ),
        ROSTER,
    )

    assert draft.tables[0].rows[0].value is None
    (issue,) = issues_of(draft, IssueType.UNPARSED_VALUE)
    assert issue.raw_value == "ilegível"


def test_garbage_that_happens_to_parse_is_caught_by_the_cross_check():
    """The dangerous misreading is the one that still looks like a number.

    "3S6.SO" for "356.50" parses as 3, quietly and wrongly. Nothing about the
    string says so -- what says so is that the app put that line first and a 3
    does not come first.
    """
    draft = review(
        assemble(
            [
                extraction(
                    Modality.HUSTLE,
                    Period.MONTH,
                    [("Arthur", "3S6.SO", 1), ("Túlio", "185.17 pontos", 2)],
                )
            ]
        ),
        ROSTER,
    )

    assert draft.tables[0].rows[0].value == 3.0
    assert {issue.name for issue in issues_of(draft, IssueType.POSITION_MISMATCH)} == {
        "Arthur",
        "Túlio",
    }


# -- the cross-check against the app's own numbering -----------------------


def test_a_line_read_out_of_order_is_flagged():
    """Both lines light up, because either one could be the misreading.

    The app said Arthur is 1st and Túlio 2nd; the values say the opposite. The
    screen cannot know which number was misread, and pretending it can would
    point the admin at the wrong line half the time.
    """
    draft = review(
        assemble(
            [
                extraction(
                    Modality.HUSTLE,
                    Period.MONTH,
                    [("Arthur", "356.50 pontos", 1), ("Túlio", "500.00 pontos", 2)],
                )
            ]
        ),
        ROSTER,
    )

    flagged = {
        issue.name: (issue.reported, issue.expected)
        for issue in issues_of(draft, IssueType.POSITION_MISMATCH)
    }
    assert flagged == {"Arthur": (1, 2), "Túlio": (2, 1)}


def test_the_calorie_cross_check_uses_the_raw_order():
    """The app numbers the calorie list without knowing about the bonus.

    Lorrana has the bonus and Arthur does not: 7,325 * 1.2 beats 8,059, so the
    tally will put her first. The screenshot still says Arthur is 1st, and it
    is right -- checking against the adjusted order would light up most of the
    calorie table every month and teach the admin to ignore the highlight
    exactly where it matters most.
    """
    draft = review(
        assemble(
            [
                extraction(
                    Modality.CALORIES,
                    Period.MONTH,
                    [("Arthur", "8,059 calorias", 1), ("Lorrana", "7,325 calorias", 2)],
                )
            ]
        ),
        ROSTER,
    )

    assert issues_of(draft, IssueType.POSITION_MISMATCH) == []


def test_a_shared_position_is_not_a_mismatch():
    """Competition ranking: two equal values are both 1st."""
    draft = review(
        assemble(
            [
                extraction(
                    Modality.ACTIVE_DAYS,
                    Period.MONTH,
                    [("Arthur", "26 dias", 1), ("Túlio", "26 dias", 1)],
                )
            ]
        ),
        ROSTER,
    )

    assert issues_of(draft, IssueType.POSITION_MISMATCH) == []


def test_a_row_the_app_did_not_number_is_not_cross_checked():
    draft = review(
        assemble(
            [extraction(Modality.HUSTLE, Period.MONTH, [("Arthur", "10 pontos", None)])]
        ),
        ROSTER,
    )

    assert issues_of(draft, IssueType.POSITION_MISMATCH) == []


# -- handing it to the tally -----------------------------------------------


def test_the_corrected_draft_becomes_leaderboards():
    draft = review(
        assemble(
            [
                extraction(
                    Modality.HUSTLE,
                    Period.MONTH,
                    [
                        ("Arthur Pereira", "356.50 pontos", 1),
                        ("Tulio", "185.17 pontos", 2),
                    ],
                ),
                extraction(
                    Modality.DISTANCE,
                    Period.YEAR,
                    [("Arthur", "893.06 quilômetros", 1)],
                ),
            ]
        ),
        ROSTER,
        month="2026-06",
    )

    tables = to_tables(draft)

    assert tables.value_for("Arthur", Modality.HUSTLE) == 356.50
    assert tables.value_for("Arthur", Modality.DISTANCE, Period.YEAR) == 893.06
    assert tables.get(Modality.HUSTLE)[0].reported_position == 1
    assert draft.month == "2026-06"


def test_a_row_nobody_could_understand_stays_out_of_the_tally():
    """It is on the screen with an issue attached; it is not in the numbers."""
    draft = review(
        assemble(
            [
                extraction(
                    Modality.HUSTLE,
                    Period.MONTH,
                    [("Arthur", "356.50 pontos", 1), ("Quem?", "ilegível", 2)],
                )
            ]
        ),
        ROSTER,
    )

    assert [entry.name for entry in to_tables(draft).get(Modality.HUSTLE)] == ["Arthur"]


def test_a_table_whose_header_is_unknown_is_not_tallied():
    draft = review(
        assemble([extraction(None, None, [("Arthur", "10 pontos", 1)])]), ROSTER
    )

    assert to_tables(draft).data == {}
