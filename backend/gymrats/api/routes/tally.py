"""Seeing the result, then committing it.

``preview`` writes nothing. ``commit`` is the only route in the system that
changes ``data/``, and it does it in one order: store the reviewed
leaderboards, republish the site's JSON, retire the screenshots.

Issues never block a commit. The admin is the final authority -- the review
screen is what insists on being looked at, not the API.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...collection.client import CollectorError
from ...collection.service import bounds
from ...review.assemble import review, to_tables
from ...storage.schema import (
    draft_to_dict,
    tally_result_to_dict,
)
from ..deps import Wiring
from ..schemas import TallyIn
from .ocr import tables_from_body

router = APIRouter(prefix="/tally")


def _reviewed(body: TallyIn, services: Wiring):
    return review(
        tables_from_body(body.draft), services.repo.participants(), month=body.month
    )


@router.post("/preview")
def preview(body: TallyIn, services: Wiring) -> dict:
    draft = _reviewed(body, services)
    result = services.tally.preview(body.month, to_tables(draft))
    return {
        **tally_result_to_dict(result.month, result.season),
        "issues": draft_to_dict(draft)["issues"],
        "committed": False,
    }


@router.post("/commit")
def commit(body: TallyIn, services: Wiring) -> dict:
    try:
        bounds(body.month)
    except CollectorError as exc:
        raise HTTPException(409, str(exc)) from None
    draft = _reviewed(body, services)
    result = services.tally.commit(body.month, to_tables(draft))

    if body.batch:
        # Out of the pending list, but moved rather than deleted: a month that
        # has to be re-tallied needs the screenshots it was made from.
        for item in services.source.list_pending():
            if item.batch == body.batch:
                services.source.mark_processed(item)
        services.drafts.clear(body.batch)

    return {
        **tally_result_to_dict(result.month, result.season),
        "issues": draft_to_dict(draft)["issues"],
        "committed": True,
        "month_path": str(result.month_path),
        "published": [str(path) for path in result.published],
    }
