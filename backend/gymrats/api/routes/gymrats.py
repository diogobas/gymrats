"""Local admin API: credentials stay behind this boundary."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...collection.client import CollectorError
from ..deps import Wiring
from ..schemas import DraftIn
from .ocr import tables_from_body

router = APIRouter(prefix="/gymrats")


class EmailIn(BaseModel):
    email: str


class CodeIn(BaseModel):
    code: str


class MonthIn(BaseModel):
    month: str
    provisional: bool = False


class RevisionIn(BaseModel):
    revision: int


class CorrectionIn(DraftIn):
    revision: int


class CommitIn(RevisionIn):
    preview_token: str
    replace: bool = False


def call(action, *args):
    try:
        return action(*args)
    except CollectorError as exc:
        raise HTTPException(409, str(exc)) from None
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(
            422, "Falha ao ler ou salvar dados locais. Nenhuma credencial foi exibida."
        ) from None


@router.get("/session")
def session(services: Wiring):
    return services.gymrats.session.status()


@router.post("/session/code")
def request_code(body: EmailIn, services: Wiring):
    return call(services.gymrats.session.request_code, body.email.strip())


@router.post("/session/verify")
def verify_code(body: CodeIn, services: Wiring):
    return call(services.gymrats.session.verify, body.code.strip())


@router.delete("/session")
def disconnect(services: Wiring):
    return services.gymrats.session.disconnect()


@router.get("/runs")
def list_runs(services: Wiring):
    return {"runs": services.gymrats.list()}


@router.post("/runs", status_code=202)
def start_run(body: MonthIn, services: Wiring):
    return call(services.gymrats.start, body.month, body.provisional)


@router.get("/runs/{run}")
def get_run(run: str, services: Wiring):
    return call(services.gymrats.get, run)


@router.get("/runs/{run}/draft")
def get_draft(run: str, services: Wiring):
    return call(services.gymrats.load_draft, run)


@router.put("/runs/{run}/draft")
def save_draft(run: str, body: CorrectionIn, services: Wiring):
    return call(
        services.gymrats.save_draft,
        run,
        tables_from_body(body),
        body.month,
        body.revision,
    )


@router.post("/runs/{run}/preview")
def preview(run: str, body: RevisionIn, services: Wiring):
    return call(services.gymrats.preview, run, body.revision)


@router.post("/runs/{run}/commit")
def commit(run: str, body: CommitIn, services: Wiring):
    return call(
        services.gymrats.commit, run, body.revision, body.preview_token, body.replace
    )
