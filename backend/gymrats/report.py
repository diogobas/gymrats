"""Print a tally as a table, for checking against the app's screenshots.

    uv run python -m gymrats.report
    uv run python -m gymrats.report --month 2026-06

Deliberately stdlib-only and read-only: it writes nothing, so it is safe to
run against real data while the rest of the system is still being built.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .core.models import SCORING_MODALITIES, Modality, MonthResult, SeasonResult
from .core.scoring import tally_month
from .core.season import build_season
from .storage.repository import Repository
from .storage.schema import format_duration

BOLD, DIM, YELLOW, RESET = "\033[1m", "\033[2m", "\033[33m", "\033[0m"

MODALITY_HEADER = {
    Modality.HUSTLE: "hustle",
    Modality.ACTIVE_DAYS: "dias",
    Modality.CALORIES: "cal",
}


def _rule(width: int) -> str:
    return DIM + "─" * width + RESET


def _print_tiebreaks(rows, *, scope: str) -> None:
    """One line per tie, not one per person.

    Everyone in a tied group carries the same TiebreakInfo, so printing per
    row would say the same thing twice.
    """
    seen: set[frozenset[str]] = set()
    for row in rows:
        if row.tiebreak is None:
            continue
        group = frozenset({row.name, *row.tiebreak.tied_with})
        if group in seen:
            continue
        seen.add(group)

        names = " x ".join(sorted(group, key=lambda n: n != row.name))
        criterion = row.tiebreak.resolved_by

        if criterion is None:
            print(
                f"{YELLOW}  ! {names}: empate em {row.total} pts que a cascata "
                f"não separou — decisão sua{RESET}"
            )
            continue

        label = "distância" if criterion is Modality.DISTANCE else "duração"
        compared = ", ".join(
            f"{name} {value:,.2f} km"
            if criterion is Modality.DISTANCE
            else f"{name} {format_duration(value)}"
            for name, value in sorted(
                row.tiebreak.comparison.items(), key=lambda item: item[1], reverse=True
            )
        )
        print(f"{DIM}  {names} ({row.total} pts): {label} {scope} — {compared}{RESET}")


def print_month(result: MonthResult) -> None:
    print(f"\n{BOLD}CLASSIFICAÇÃO — {result.month}{RESET}")
    print(_rule(78))
    print(
        f"{'#':>2}  {'nome':<10}{'pts':>4}   "
        f"{'hustle':>6} {'dias':>5} {'cal':>5}   "
        f"{'valor hustle':>12} {'dias':>5} {'kcal':>7} {'km':>8} {'tempo':>8}"
    )
    print(_rule(78))

    for row in result.standings:
        positions = "".join(
            f"{row.positions[modality]:>7}" if modality is Modality.HUSTLE
            else f"{row.positions[modality]:>6}"
            for modality in SCORING_MODALITIES
        )
        bonus = "*" if row.calorie_bonus_applied else " "
        print(
            f"{row.position:>2}. {row.name:<10}{row.total:>3}   {positions}   "
            f"{row.values[Modality.HUSTLE]:>12.2f}"
            f"{int(row.values[Modality.ACTIVE_DAYS] or 0):>6}"
            f"{int(row.values[Modality.CALORIES] or 0):>7}{bonus}"
            f"{row.values[Modality.DISTANCE] or 0:>8.2f}"
            f"{format_duration(row.values[Modality.DURATION]) or '-':>8}"
        )

    print(_rule(78))
    print(f"{DIM}* bônus de +20% aplicado nas calorias antes de ordenar{RESET}")

    _print_tiebreaks(result.standings, scope="no mês")

    if result.excluded:
        names = ", ".join(item.name for item in result.excluded)
        print(f"{DIM}  excluídos por 0 hustle: {names}{RESET}")


def print_season(season: SeasonResult) -> None:
    print(f"\n{BOLD}PONTOS CORRIDOS — {season.year}{RESET}")
    print(_rule(78))
    header = "".join(f"{month[-2:]:>5}" for month in season.months)
    print(f"{'#':>2}  {'nome':<10}{'total':>6}   {header}")
    print(_rule(78))

    for row in season.rows:
        columns = "".join(
            f"{row.by_month[month]:>4}" + ("*" if month in row.imputed_months else " ")
            for month in season.months
        )
        print(f"{row.position:>2}. {row.name:<10}{row.total:>5}   {columns}")

    print(_rule(78))
    print(f"{DIM}* não competiu — recebeu a posição do último colocado + 1{RESET}")

    _print_tiebreaks(season.rows, scope="no ano")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data", type=Path)
    parser.add_argument("--month", default=None, help="default: the latest tallied")
    parser.add_argument("--year", default=None, type=int)
    args = parser.parse_args(argv)

    repo = Repository(args.data)
    months = repo.months()
    if not months:
        parser.error(f"no tallied months under {args.data}/months/")

    month = args.month or months[-1]
    year = args.year or int(month[:4])

    participants = repo.participants()
    tables = repo.tables(month)
    result = tally_month(month, tables, participants)
    print_month(result)

    tallied = [tally_month(key, repo.tables(key), participants) for key in months]
    season = build_season(year, [*repo.history_results(year), *tallied], tables)
    print_season(season)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
