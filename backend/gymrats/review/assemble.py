"""From screenshots to a draft, and from a corrected draft to leaderboards.

Three steps, kept separate because the middle one runs again after every edit
the admin makes:

``assemble``   groups the extractions by leaderboard and merges the parts
``review``     resolves names, parses values, cross-checks positions
``to_tables``  hands the corrected draft to the tally
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..core.models import Entry, Modality, Participant, Period, Tables
from ..core.ranking import competition_rank
from ..core.roster import Roster
from ..core.values import ParseError, normalize_name, parse_value
from ..ocr.models import Extraction
from .models import Draft, DraftRow, DraftTable, Issue, IssueType

__all__ = ["assemble", "review", "to_tables"]


# --------------------------------------------------------------------------
# 1. group the screenshots into leaderboards
# --------------------------------------------------------------------------


def assemble(extractions: Iterable[Extraction]) -> tuple[DraftTable, ...]:
    """Merge the extractions into one table per leaderboard.

    A list too long for one screen arrives as two screenshots; they are joined
    here and deduplicated by name, because the overlap between the two parts is
    the normal case, not a mistake.

    Screenshots whose header could not be identified are kept as their own
    table -- dropping them would hide the problem, and guessing which
    leaderboard they belong to is exactly what this system does not do.
    """
    grouped: dict[tuple[Modality | None, Period | None], list[Extraction]] = {}
    unidentified: list[Extraction] = []

    for extraction in extractions:
        if extraction.modality is None or extraction.period is None:
            unidentified.append(extraction)
            continue
        grouped.setdefault((extraction.modality, extraction.period), []).append(
            extraction
        )

    tables = [
        _merge(modality, period, parts) for (modality, period), parts in grouped.items()
    ]
    tables.extend(
        _merge(extraction.modality, extraction.period, [extraction])
        for extraction in unidentified
    )
    return tuple(tables)


def _merge(
    modality: Modality | None,
    period: Period | None,
    parts: Sequence[Extraction],
) -> DraftTable:
    rows: list[DraftRow] = []
    seen: dict[str, int] = {}  # normalised name -> index in rows

    for extraction in parts:
        for row in extraction.rows:
            key = normalize_name(row.name)
            index = seen.get(key)
            if index is None:
                seen[key] = len(rows)
                rows.append(
                    DraftRow(
                        name=row.name, raw_value=row.raw_value, position=row.position
                    )
                )
                continue
            # Same person twice. Identical is just the overlap between two
            # screenshots of one list; different is a real conflict, and
            # `review` raises it as an issue rather than picking a winner.
            existing = rows[index]
            if existing.raw_value != row.raw_value:
                rows.append(
                    DraftRow(
                        name=row.name, raw_value=row.raw_value, position=row.position
                    )
                )

    return DraftTable(
        modality=modality,
        period=period,
        rows=tuple(rows),
        sources=tuple(
            extraction.item_id for extraction in parts if extraction.item_id is not None
        ),
    )


# --------------------------------------------------------------------------
# 2. understand it, and say what looks wrong
# --------------------------------------------------------------------------


def review(
    tables: Iterable[DraftTable],
    participants: Iterable[Participant],
    *,
    month: str | None = None,
) -> Draft:
    """Resolve, parse, cross-check. Runs again after every correction."""
    roster = Roster(participants)
    reviewed: list[DraftTable] = []
    issues: list[Issue] = []

    for index, table in enumerate(tables):
        rows = tuple(_understand(row, table.modality, roster) for row in table.rows)
        reviewed.append(
            DraftTable(
                modality=table.modality,
                period=table.period,
                rows=rows,
                sources=table.sources,
            )
        )
        issues.extend(_issues_for(index, table.modality, table.period, rows))

    return Draft(month=month, tables=tuple(reviewed), issues=tuple(issues))


def _understand(row: DraftRow, modality: Modality | None, roster: Roster) -> DraftRow:
    resolution = roster.resolve(row.name)
    value: float | None = None
    if modality is not None:
        try:
            value = parse_value(modality, row.raw_value)
        except ParseError:
            # Deliberately not zero: an unreadable value becomes an issue and
            # a human decides.
            value = None
    return DraftRow(
        name=row.name,
        raw_value=row.raw_value,
        position=row.position,
        resolved_name=resolution.canonical,
        value=value,
    )


def _is_blank(row: DraftRow) -> bool:
    """A row with nothing typed into it yet.

    The review screen adds empty rows as you go. Flagging one the moment it
    appears -- unknown name, unreadable value -- would fill the screen with
    complaints about work not started, and teach the admin to scroll past
    exactly the highlights that matter.
    """
    return not row.name.strip() and not row.raw_value.strip()


def _issues_for(
    table: int,
    modality: Modality | None,
    period: Period | None,
    rows: Sequence[DraftRow],
) -> list[Issue]:
    issues: list[Issue] = []

    if modality is None:
        issues.append(Issue(IssueType.MISSING_MODALITY, period=period, table=table))
    if period is None:
        issues.append(Issue(IssueType.MISSING_PERIOD, modality=modality, table=table))

    for index, row in enumerate(rows):
        if _is_blank(row):
            continue
        if row.resolved_name is None:
            issues.append(
                Issue(
                    IssueType.UNKNOWN_NAME,
                    modality,
                    period,
                    table=table,
                    row=index,
                    name=row.name,
                )
            )
        if modality is not None and row.value is None:
            issues.append(
                Issue(
                    IssueType.UNPARSED_VALUE,
                    modality,
                    period,
                    table=table,
                    row=index,
                    name=row.name,
                    raw_value=row.raw_value,
                )
            )

    issues.extend(_duplicates(table, modality, period, rows))
    issues.extend(_position_mismatches(table, modality, period, rows))
    return issues


def _duplicates(
    table: int,
    modality: Modality | None,
    period: Period | None,
    rows: Sequence[DraftRow],
) -> list[Issue]:
    counted: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        if _is_blank(row):
            continue
        counted.setdefault(row.resolved_name or normalize_name(row.name), []).append(
            index
        )

    return [
        Issue(
            IssueType.DUPLICATE_NAME,
            modality,
            period,
            table=table,
            row=indexes[-1],
            name=rows[indexes[-1]].name,
        )
        for indexes in counted.values()
        if len(indexes) > 1
    ]


def _position_mismatches(
    table: int,
    modality: Modality | None,
    period: Period | None,
    rows: Sequence[DraftRow],
) -> list[Issue]:
    """Compare the app's own numbering against the order the values imply.

    Against the RAW order, always. GymRats prints those numbers knowing nothing
    about the +20% calorie bonus, so checking the adjusted order would flag
    most of the calorie table every single month -- and an alarm that cries
    wolf where it matters most is worse than no alarm.
    """
    # Keyed by index, not by name: a duplicated name must not collapse two
    # rows into one before the ranking is even computed.
    ranked = [
        (str(index), row.value) for index, row in enumerate(rows) if row.value is not None
    ]
    if not ranked:
        return []

    computed = competition_rank(ranked)

    issues: list[Issue] = []
    for index, row in enumerate(rows):
        if row.value is None or row.position is None:
            continue
        expected = computed[str(index)]
        if expected != row.position:
            issues.append(
                Issue(
                    IssueType.POSITION_MISMATCH,
                    modality,
                    period,
                    table=table,
                    row=index,
                    name=row.name,
                    expected=expected,
                    reported=row.position,
                )
            )
    return issues


# --------------------------------------------------------------------------
# 3. hand it to the tally
# --------------------------------------------------------------------------


def to_tables(draft: Draft) -> Tables:
    """The corrected draft as the leaderboards the core expects.

    Rows nobody could resolve, and values nobody could read, are left out: they
    have issues attached and the admin saw them. Leaving a half-understood row
    in would put a name the roster does not know into the tally.
    """
    raw: dict[tuple[Modality, Period], tuple[Entry, ...]] = {}
    for table in draft.tables:
        if table.modality is None or table.period is None:
            continue
        entries = tuple(
            Entry(
                name=row.resolved_name,
                value=row.value,
                reported_position=row.position,
            )
            for row in table.rows
            if row.resolved_name is not None and row.value is not None
        )
        if entries:
            raw[(table.modality, table.period)] = entries
    return Tables.build(raw)
