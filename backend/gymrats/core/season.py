"""The season table -- "pontos corridos".

One column per month holding the person's FINAL POSITION that month. Someone
who did not compete -- new to the group, absent, or excluded for zero hustle
-- takes last place's position plus one, computed per month and applied
retroactively to every month already played.

Total is the sum of the columns; the lowest total leads. The season tiebreak
runs the same cascade as the month, against the annual snapshot through month end.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .models import MonthResult, Period, SeasonResult, SeasonRow, Tables
from .tiebreak import order_with_tiebreaks

__all__ = ["absentee_score", "build_season"]


def absentee_score(result: MonthResult) -> int:
    """What a non-competitor scores for ``result``'s month: last place + 1."""
    return result.last_position + 1


def _season_names(results: Sequence[MonthResult]) -> tuple[str, ...]:
    """Everyone who competed in at least one month of the season.

    Someone on the roster who never competed all year does not appear at all;
    someone who joined in April is carried back to January with the absentee
    score for each month before they arrived.
    """
    seen: dict[str, None] = {}
    for result in results:
        for row in result.standings:
            seen.setdefault(row.name, None)
    return tuple(seen)


def build_season(
    year: int,
    results: Iterable[MonthResult],
    year_tables: Tables | None = None,
    *,
    eligible_names: Sequence[str] | None = None,
    source_url: str | None = None,
) -> SeasonResult:
    """Accumulate ``results`` into the season table.

    ``year_tables`` supplies distance and duration from January 1 through the
    last day of the most recently tallied month. The collector records that
    cutoff; the core consumes the supplied snapshot without fetching data.
    Legacy screenshot snapshots remain unchanged until reviewed.

    ``eligible_names`` restricts a historical season to the official roster;
    other participants remain in their monthly results. Absences always score
    last place + 1, including historical seasons.
    """
    ordered_results = sorted(results, key=lambda result: result.month)
    months = tuple(result.month for result in ordered_results)
    names = (
        tuple(eligible_names)
        if eligible_names is not None
        else _season_names(ordered_results)
    )
    if len(set(names)) != len(names) or any(not name for name in names):
        raise ValueError("Season participants must have unique, nonempty names")

    if not names or not months:
        return SeasonResult(year=year, months=months, rows=())

    absentee = {result.month: absentee_score(result) for result in ordered_results}

    by_month: dict[str, dict[str, int]] = {}
    imputed: dict[str, list[str]] = {}
    for name in names:
        columns: dict[str, int] = {}
        missed: list[str] = []
        for result in ordered_results:
            position = result.position_of(name)
            if position is None:
                position = absentee[result.month]
                missed.append(result.month)
            columns[result.month] = position
        by_month[name] = columns
        imputed[name] = missed

    totals = {name: sum(by_month[name].values()) for name in names}

    groups: list[tuple[int, list[str]]] = []
    for score in sorted(set(totals.values())):
        groups.append((score, [name for name in names if totals[name] == score]))

    tables = year_tables if year_tables is not None else Tables.build({})
    ordered, unresolved = order_with_tiebreaks(groups, tables, Period.YEAR)

    rows = tuple(
        SeasonRow(
            position=position,
            name=name,
            total=totals[name],
            by_month=dict(by_month[name]),
            imputed_months=tuple(imputed[name]),
            tiebreak=tiebreak,
        )
        for position, name, tiebreak in ordered
    )

    return SeasonResult(
        year=year,
        months=months,
        rows=rows,
        unresolved_ties=tuple(unresolved),
        source_url=source_url,
    )
