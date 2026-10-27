"""Wiring.

One place builds the source, the engine, the repository and the services, and
the routes ask for them. Swapping a plugin is a setting, not an import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from ..collection.service import CollectionService
from ..ingestion.registry import build_source
from ..ingestion.source import ScreenshotSource
from ..ingestion.upload import UploadSource
from ..ocr.engine import OcrEngine
from ..ocr.registry import build_engine
from ..storage.drafts import DraftStore
from ..storage.publisher import Publisher
from ..storage.repository import Repository
from ..storage.tally_service import TallyService
from .config import Settings

__all__ = ["Services", "get_services", "get_upload_source"]


@dataclass
class Services:
    settings: Settings
    repo: Repository
    source: ScreenshotSource
    engine: OcrEngine
    drafts: DraftStore
    tally: TallyService
    gymrats: CollectionService

    @classmethod
    def build(cls, settings: Settings) -> Services:
        repo = Repository(settings.data)
        tally = TallyService(repo, Publisher(repo, settings.site))
        return cls(
            settings=settings,
            repo=repo,
            source=build_source(settings.source, settings.inbox),
            engine=build_engine(settings.ocr),
            drafts=DraftStore(settings.inbox),
            tally=tally,
            gymrats=CollectionService(settings.private, repo, tally),
        )


def get_services(request: Request) -> Services:
    return request.app.state.services


Wiring = Annotated[Services, Depends(get_services)]


def get_upload_source(services: Wiring) -> UploadSource:
    """The upload route needs the one source that can receive files.

    Only one source is active at a time. Saying which one is active beats a
    404 on a route that exists.
    """
    if not isinstance(services.source, UploadSource):
        raise HTTPException(
            status_code=409,
            detail=(
                f"a fonte ativa é {services.settings.source!r}, que não recebe "
                "upload — use POST /api/ingest/scan"
            ),
        )
    return services.source


Uploads = Annotated[UploadSource, Depends(get_upload_source)]
