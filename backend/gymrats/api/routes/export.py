"""The month as a CSV, to paste into the spreadsheet.

Headers in Portuguese: this one is read by a person, in Google Sheets, next to
the sheet the tally used to live in. Numbers go out with a dot as the decimal
separator so Sheets reads them as numbers rather than text.
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Response

from ...core.models import SCORING_MODALITIES, Modality
from ...core.scoring import tally_month
from ...storage.schema import format_duration
from ..deps import Wiring

router = APIRouter(prefix="/export")

HEADER = [
    "posicao",
    "nome",
    "pontos",
    "pos_hustle",
    "pos_dias",
    "pos_calorias",
    "hustle",
    "dias_ativos",
    "calorias",
    "calorias_com_bonus",
    "bonus",
    "distancia_km",
    "duracao_min",
    "duracao",
]


@router.get("/{month}.csv")
def export_month(month: str, services: Wiring) -> Response:
    path = services.repo.month_path(month)
    if not path.is_file():
        raise HTTPException(404, f"{month} ainda não foi apurado")

    result = tally_month(month, services.repo.tables(month), services.repo.participants())

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADER)
    for row in result.standings:
        writer.writerow(
            [
                row.position,
                row.name,
                row.total,
                *(row.positions.get(modality) for modality in SCORING_MODALITIES),
                row.values.get(Modality.HUSTLE),
                row.values.get(Modality.ACTIVE_DAYS),
                row.values.get(Modality.CALORIES),
                row.calories_adjusted,
                "sim" if row.calorie_bonus_applied else "não",
                row.values.get(Modality.DISTANCE),
                row.values.get(Modality.DURATION),
                format_duration(row.values.get(Modality.DURATION)),
            ]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="gymrats-{month}.csv"'},
    )
