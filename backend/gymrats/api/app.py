"""The API. Thin on purpose.

Routes validate, call one thing, and serialise. Every rule lives below them --
in ``review`` for the draft, in ``core`` for the tally, in ``storage`` for what
gets written. If a route grows a second decision, it belongs somewhere else.

It listens on 0.0.0.0 and allows local-network origins, because the phone
holding the screenshots is not this machine.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from .config import Settings
from .deps import Services
from .routes import export, health, ingest, ocr, participants, tally

__all__ = ["create_app"]

#: localhost plus the three private ranges. The admin's laptop and phone are
#: on the same wifi; nothing outside it should be talking to this at all.
LOCAL_NETWORK_ORIGINS = (
    r"http://(localhost|127\.0\.0\.1"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})"
    r"(:\d+)?"
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="GymRats — apuração",
        version=__version__,
        description="Roda local, uma vez por mês. Não vai para produção.",
    )
    app.state.services = Services.build(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=LOCAL_NETWORK_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module in (health, participants, ingest, ocr, tally, export):
        app.include_router(module.router, prefix="/api")

    return app
