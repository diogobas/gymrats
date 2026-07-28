"""Reading a batch, and keeping the corrections.

The engine runs once, when the batch is read. After that every edit goes
through ``review`` again -- resolving names, parsing values and cross-checking
positions against what the app printed -- so a correction is judged by the
same rules as the original reading.

The draft is saved beside the screenshots. The review happens on a phone,
across ten leaderboards, and a discarded tab should not cost twenty
corrections.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, HTTPException

from ...ocr.engine import OcrError
from ...review.assemble import assemble, review
from ...review.models import DraftRow, DraftTable
from ...storage.schema import draft_to_dict
from ..deps import Wiring
from ..schemas import DraftIn

router = APIRouter(prefix="/ocr")


def tables_from_body(body: DraftIn) -> tuple[DraftTable, ...]:
    return tuple(
        DraftTable(
            modality=table.modality,
            period=table.period,
            rows=tuple(
                DraftRow(name=row.name, raw_value=row.raw_value, position=row.position)
                for row in table.rows
            ),
            sources=tuple(table.sources),
        )
        for table in body.tables
    )


@router.post("/{batch}")
def read_batch(batch: str, services: Wiring, month: str | None = None) -> dict:
    """Run the engine over every pending screenshot in the batch.

    With the manual engine every table comes back empty and the admin types
    what the screenshot shows. Step 4 changes the engine and nothing else.
    """
    items = [item for item in services.source.list_pending() if item.batch == batch]
    if not items:
        raise HTTPException(404, f"lote sem prints pendentes: {batch}")

    extractions = []
    for item in items:
        try:
            extraction = services.engine.extract(services.source.fetch(item))
        except OcrError as error:
            raise HTTPException(422, f"{item.id}: {error}") from error
        # The engine reads pixels and is handed nothing else; which screenshot
        # they came from is the ingestion layer's business, stamped here.
        extractions.append(replace(extraction, item_id=item.id))

    draft = review(assemble(extractions), services.repo.participants(), month=month)
    services.drafts.save(batch, draft)
    return draft_to_dict(draft)


@router.get("/{batch}/draft")
def get_draft(batch: str, services: Wiring) -> dict:
    stored = services.drafts.load(batch)
    if stored is None:
        raise HTTPException(404, f"nenhum rascunho salvo para {batch}")
    # Re-reviewed on the way out: a draft written before a participant was
    # registered should not still call that name unknown.
    draft = review(stored.tables, services.repo.participants(), month=stored.month)
    return draft_to_dict(draft)


@router.put("/{batch}/draft")
def save_draft(batch: str, body: DraftIn, services: Wiring) -> dict:
    draft = review(tables_from_body(body), services.repo.participants(), month=body.month)
    services.drafts.save(batch, draft)
    return draft_to_dict(draft)
