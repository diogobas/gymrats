"""Mapping between the core dataclasses and the JSON on disk.

Two distinct shapes live here:

* the INPUT under ``data/months/YYYY-MM.json`` -- the reviewed leaderboards,
  hand-editable, the source of truth. Results are always recomputable from it.
* the PUBLISHED output under ``frontend/public/data/`` -- read-only, consumed
  by the static site.

Presentation belongs to the published shape, not to the core: the core emits a
structured ``TiebreakInfo`` and the Portuguese sentence the competitors read is
rendered here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ..core.models import (
    SCORING_MODALITIES,
    Entry,
    Modality,
    MonthResult,
    Participant,
    Period,
    SeasonResult,
    Standing,
    Tables,
    TiebreakInfo,
)
from ..review.models import Draft, DraftRow, DraftTable, Issue, IssueType

__all__ = [
    "SCHEMA_VERSION",
    "draft_from_dict",
    "draft_to_dict",
    "issue_to_dict",
    "month_result_to_dict",
    "participants_from_dict",
    "participants_to_dict",
    "season_result_to_dict",
    "tables_from_dict",
    "tables_to_dict",
]

SCHEMA_VERSION = 1

_MODALITY_LABEL_PT = {
    Modality.HUSTLE: "hustle points",
    Modality.ACTIVE_DAYS: "dias ativos",
    Modality.CALORIES: "calorias",
    Modality.DISTANCE: "distância",
    Modality.DURATION: "duração",
}


# --------------------------------------------------------------------------
# input shape
# --------------------------------------------------------------------------


def participants_from_dict(payload: Mapping[str, Any]) -> tuple[Participant, ...]:
    return tuple(
        Participant(
            name=item["name"],
            aliases=tuple(item.get("aliases", ())),
            calorie_bonus=bool(item.get("calorie_bonus", False)),
        )
        for item in payload.get("participants", ())
    )


def participants_to_dict(participants: Iterable[Participant]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "participants": [
            {
                "name": person.name,
                "aliases": list(person.aliases),
                "calorie_bonus": person.calorie_bonus,
            }
            for person in participants
        ],
    }


def tables_from_dict(payload: Mapping[str, Any]) -> Tables:
    """Read the ``tables`` block of a month input file."""
    raw: dict[tuple[Modality, Period], tuple[Entry, ...]] = {}
    for modality_key, periods in (payload.get("tables") or {}).items():
        # These files are meant to be opened and edited by hand, so keys
        # starting with "_" are reserved for notes and never parsed.
        if modality_key.startswith("_"):
            continue
        modality = Modality(modality_key)
        for period_key, rows in (periods or {}).items():
            if period_key.startswith("_"):
                continue
            period = Period(period_key)
            raw[(modality, period)] = tuple(
                Entry(
                    name=row["name"],
                    value=float(row["value"]),
                    reported_position=row.get("reported_position"),
                )
                for row in rows
            )
    ignore_hustle = payload.get("ignore_hustle", False)
    if type(ignore_hustle) is not bool:
        raise ValueError("ignore_hustle must be a boolean")
    official = payload.get("official_result")
    result = None
    if official is not None:
        rows = []
        names = set()
        previous_total = -1
        scoring_modalities = None
        for index, row in enumerate(official["standings"], 1):
            positions = {Modality(key): value for key, value in row["positions"].items()}
            if scoring_modalities is None:
                scoring_modalities = set(positions)
            if (
                row["position"] != index
                or row["name"] in names
                or not row["name"]
                or set(positions)
                not in (
                    set(SCORING_MODALITIES),
                    {*SCORING_MODALITIES, Modality.DURATION},
                )
                or set(positions) != scoring_modalities
                or any(
                    type(value) is not int or value <= 0 for value in positions.values()
                )
                or row["total"] != sum(positions.values())
                or row["total"] < previous_total
            ):
                raise ValueError("Invalid official monthly standings")
            names.add(row["name"])
            previous_total = row["total"]
            values = row["values"]
            rows.append(
                Standing(
                    position=row["position"],
                    name=row["name"],
                    total=row["total"],
                    positions=positions,
                    values={
                        modality: values.get(modality.value) for modality in Modality
                    },
                    calories_adjusted=row["calories_adjusted"],
                    calorie_bonus_applied=row["calorie_bonus_applied"],
                )
            )
        if not rows or not official.get("source_url"):
            raise ValueError("Official standings require rows and a source URL")
        result = MonthResult(
            month=payload["month"],
            standings=tuple(rows),
            source_url=official["source_url"],
        )
    return Tables.build(raw, ignore_hustle=ignore_hustle, official_result=result)


def tables_to_dict(tables: Tables) -> dict[str, Any]:
    out: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for (modality, period), entries in sorted(
        tables.data.items(), key=lambda item: (item[0][0].value, item[0][1].value)
    ):
        out.setdefault(modality.value, {})[period.value] = [
            {
                "name": entry.name,
                "value": entry.value,
                "reported_position": entry.reported_position,
            }
            for entry in entries
        ]
    return out


# --------------------------------------------------------------------------
# published shape
# --------------------------------------------------------------------------


def _as_int(value: float | None) -> int | None:
    """Whole-number fields ship as ints, so the site never renders "24.0 dias"."""
    return None if value is None else round(value)


def format_duration(minutes: float | None) -> str | None:
    if minutes is None:
        return None
    total = round(minutes)
    return f"{total // 60}h{total % 60:02d}"


def _format_criterion_value(modality: Modality, value: float) -> str:
    if modality is Modality.DURATION:
        return format_duration(value) or "-"
    if modality is Modality.DISTANCE:
        return f"{value:,.2f} km".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{value}"


def _tiebreak_to_dict(
    info: TiebreakInfo | None,
    total: int,
    period: Period,
) -> dict[str, Any] | None:
    """Render the tiebreak so the site can explain itself without extra logic."""
    if info is None:
        return None

    scope = "no mês" if period is Period.MONTH else "no ano"
    tied_with = ", ".join(info.tied_with)

    if info.resolved_by is None:
        detail = (
            f"Empate em {total} pontos com {tied_with}. "
            "A cascata de desempate não separou — decisão pendente do admin."
        )
    else:
        label = _MODALITY_LABEL_PT[info.resolved_by]
        compared = ", ".join(
            f"{name} {_format_criterion_value(info.resolved_by, value)}"
            for name, value in sorted(
                info.comparison.items(), key=lambda item: item[1], reverse=True
            )
        )
        detail = (
            f"Empate em {total} pontos com {tied_with}. "
            f"Desempatado por maior {label} {scope}: {compared}."
        )

    return {
        "tied_with": list(info.tied_with),
        "resolved_by": info.resolved_by.value if info.resolved_by else None,
        "comparison": dict(info.comparison),
        "detail": detail,
    }


def month_result_to_dict(result: MonthResult, generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "month": result.month,
        "generated_at": generated_at,
        "ranked_count": result.ranked_count,
        **({"official_source": result.source_url} if result.source_url else {}),
        **({"ignore_hustle": True} if result.ignore_hustle else {}),
        "standings": [
            {
                "position": row.position,
                "name": row.name,
                "total": row.total,
                "positions": {
                    modality.value: row.positions.get(modality)
                    for modality in dict.fromkeys((*SCORING_MODALITIES, *row.positions))
                },
                "values": {
                    "hustle": row.values[Modality.HUSTLE],
                    "active_days": _as_int(row.values[Modality.ACTIVE_DAYS]),
                    "calories": {
                        "raw": row.values[Modality.CALORIES],
                        "bonus_applied": row.calorie_bonus_applied,
                        "adjusted": row.calories_adjusted,
                    },
                    "distance_km": row.values[Modality.DISTANCE],
                    "duration_min": _as_int(row.values[Modality.DURATION]),
                    "duration_label": format_duration(row.values[Modality.DURATION]),
                },
                "tiebreak": _tiebreak_to_dict(row.tiebreak, row.total, Period.MONTH),
            }
            for row in result.standings
        ],
        "excluded": [
            {"name": item.name, "reason": item.reason.value} for item in result.excluded
        ],
        "unresolved_ties": [list(group) for group in result.unresolved_ties],
    }


# --------------------------------------------------------------------------
# the draft under review
# --------------------------------------------------------------------------

_PERIOD_LABEL_PT = {Period.MONTH: "Este mês", Period.YEAR: "Este ano"}


def _table_label(
    modality: Modality | None,
    period: Period | None,
) -> str:
    modality_label = _MODALITY_LABEL_PT.get(modality) if modality else "modalidade ?"
    period_label = _PERIOD_LABEL_PT.get(period) if period else "recorte ?"
    return f"{modality_label} · {period_label}"


def _issue_message(issue: Issue) -> str:
    """The sentence the review screen shows.

    Rendered here for the same reason the tiebreak sentence is: the review
    layer emits a structured issue, and prose is presentation.
    """
    name = issue.name or "essa linha"
    match issue.type:
        case IssueType.POSITION_MISMATCH:
            return (
                f"O app numerou {name} como {issue.reported}º, mas o valor lido "
                f"põe essa linha em {issue.expected}º. Confira o número."
            )
        case IssueType.UNKNOWN_NAME:
            return f"“{name}” não está no cadastro. Vincule a alguém ou cadastre."
        case IssueType.UNPARSED_VALUE:
            return f"Não deu para ler “{issue.raw_value}” como número."
        case IssueType.DUPLICATE_NAME:
            return f"{name} aparece duas vezes nessa tabela, com valores diferentes."
        case IssueType.MISSING_MODALITY:
            return "O cabeçalho do print não disse qual modalidade é essa."
        case IssueType.MISSING_PERIOD:
            return "O cabeçalho do print não disse se é “Este mês” ou “Este ano”."
    return "Confira essa linha."


def issue_to_dict(issue: Issue) -> dict[str, Any]:
    return {
        "type": issue.type.value,
        "modality": issue.modality.value if issue.modality else None,
        "period": issue.period.value if issue.period else None,
        "table": issue.table,
        "row": issue.row,
        "name": issue.name,
        "expected": issue.expected,
        "reported": issue.reported,
        "raw_value": issue.raw_value,
        "message": _issue_message(issue),
    }


def _draft_row_to_dict(row: DraftRow) -> dict[str, Any]:
    return {
        "name": row.name,
        "raw_value": row.raw_value,
        "position": row.position,
        "resolved_name": row.resolved_name,
        "value": row.value,
    }


def draft_to_dict(draft: Draft) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "month": draft.month,
        "tables": [
            {
                "key": table.key,
                "label": _table_label(table.modality, table.period),
                "modality": table.modality.value if table.modality else None,
                "period": table.period.value if table.period else None,
                "sources": list(table.sources),
                "rows": [_draft_row_to_dict(row) for row in table.rows],
            }
            for table in draft.tables
        ],
        "issues": [issue_to_dict(issue) for issue in draft.issues],
    }


def draft_from_dict(payload: Mapping[str, Any]) -> Draft:
    """Read back a draft, ignoring everything that is derived.

    ``resolved_name``, ``value``, the issues and the labels are all recomputed
    by ``review.review`` from the corrected rows, so a stale draft on disk
    cannot carry a stale verdict back in.
    """
    tables = tuple(
        DraftTable(
            modality=Modality(table["modality"]) if table.get("modality") else None,
            period=Period(table["period"]) if table.get("period") else None,
            rows=tuple(
                DraftRow(
                    name=row.get("name", ""),
                    raw_value=row.get("raw_value", ""),
                    position=row.get("position"),
                )
                for row in table.get("rows", ())
            ),
            sources=tuple(table.get("sources", ())),
        )
        for table in payload.get("tables", ())
    )
    return Draft(month=payload.get("month"), tables=tables)


def season_result_to_dict(result: SeasonResult, generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "year": result.year,
        "generated_at": generated_at,
        "months": list(result.months),
        "standings": [
            {
                "position": row.position,
                "name": row.name,
                "total": row.total,
                "by_month": dict(row.by_month),
                "imputed_months": list(row.imputed_months),
                "tiebreak": _tiebreak_to_dict(row.tiebreak, row.total, Period.YEAR),
            }
            for row in result.rows
        ],
        "unresolved_ties": [list(group) for group in result.unresolved_ties],
    }


def tally_result_to_dict(month, season) -> dict:
    """One response shape for screenshot and API previews."""
    from datetime import UTC, datetime

    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    return {
        "month": month_result_to_dict(month, stamp),
        "season": season_result_to_dict(season, stamp),
    }
