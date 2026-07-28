"""Getting the screenshots in, and back out for the preview.

Everything here goes through the three methods of ``ScreenshotSource``. The
routes never touch a path: an item found in ``list_pending`` is fetched by the
source that produced it, which is what keeps a future remote source from
needing anything new here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from ...ingestion.models import ScreenshotItem
from ...ingestion.upload import IncomingFile
from ..deps import Uploads, Wiring

router = APIRouter(prefix="/ingest")


def item_to_dict(item: ScreenshotItem) -> dict:
    return {
        "id": item.id,
        "batch": item.batch,
        "filename": item.filename,
        "size": item.size,
        "received_at": item.received_at,
        "content_type": item.content_type,
    }


def _find(services: Wiring, batch: str, item_id: str) -> ScreenshotItem:
    """Only ever an item the source itself listed.

    A forged identifier does not become a path here -- it simply matches
    nothing.
    """
    for item in services.source.list_pending():
        if item.batch == batch and item.id == item_id:
            return item
    raise HTTPException(404, f"print não encontrado: {batch}/{item_id}")


#: The phone's picker sends every screenshot under the same field name.
Files = Annotated[list[UploadFile], File(description="files[]")]


@router.post("/upload")
async def upload(source: Uploads, files: Files) -> dict:
    """Multipart from the phone's camera roll. One request, one batch."""
    if not files:
        raise HTTPException(400, "nenhum arquivo enviado")

    incoming = [
        IncomingFile(file.filename, await file.read(), file.content_type)
        for file in files
    ]
    batch = source.receive(incoming)
    return {
        "batch_id": batch.id,
        "items": [item_to_dict(item) for item in batch.items],
    }


@router.post("/scan")
def scan(services: Wiring) -> dict:
    """For the sources that do not receive anything: look and see what is there."""
    items = services.source.list_pending()
    batches: dict[str, list[dict]] = {}
    for item in items:
        batches.setdefault(item.batch, []).append(item_to_dict(item))
    return {
        "source": services.settings.source,
        "batches": [
            {"batch_id": batch, "items": rows} for batch, rows in sorted(batches.items())
        ],
    }


@router.get("/{batch}/items/{item_id}/image")
def image(batch: str, item_id: str, services: Wiring) -> Response:
    """The screenshot itself, for the review screen to show beside the values."""
    item = _find(services, batch, item_id)
    return Response(
        content=services.source.fetch(item),
        media_type=item.content_type or "application/octet-stream",
        headers={"Cache-Control": "no-store"},
    )
