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

from typing import Any, Iterable, Mapping

from ..core.models import (
    SCORING_MODALITIES,
    Entry,
    Modality,
    MonthResult,
    Participant,
    Period,
    SeasonResult,
    Tables,
    TiebreakInfo,
)

__all__ = [
    "SCHEMA_VERSION",
    "participants_from_dict",
    "participants_to_dict",
    "tables_from_dict",
    "tables_to_dict",
    "month_result_to_dict",
    "season_result_to_dict",
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
    return Tables.build(raw)


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
    return None if value is None else int(round(value))


def format_duration(minutes: float | None) -> str | None:
    if minutes is None:
        return None
    total = int(round(minutes))
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
        "standings": [
            {
                "position": row.position,
                "name": row.name,
                "total": row.total,
                "positions": {
                    modality.value: row.positions[modality]
                    for modality in SCORING_MODALITIES
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
