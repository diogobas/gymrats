"""The roster.

Editing it is part of reviewing: an unknown name on a screenshot is settled
either by registering a new person or by teaching the roster an alias, and
both happen here, from the phone, mid-review.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...core.models import Participant
from ...storage.schema import participants_to_dict
from ..deps import Wiring
from ..schemas import ParticipantIn, ParticipantPatch

router = APIRouter(prefix="/participants")


@router.get("")
def list_participants(services: Wiring) -> dict:
    return participants_to_dict(services.repo.participants())


@router.post("", status_code=201)
def create_participant(body: ParticipantIn, services: Wiring) -> dict:
    people = services.repo.participants()
    if any(person.name == body.name for person in people):
        raise HTTPException(409, f"{body.name} já está no cadastro")

    person = Participant(
        name=body.name,
        aliases=tuple(body.aliases),
        calorie_bonus=body.calorie_bonus,
    )
    services.repo.write_participants([*people, person])
    return participants_to_dict(services.repo.participants())


@router.patch("/{name}")
def update_participant(name: str, body: ParticipantPatch, services: Wiring) -> dict:
    people = services.repo.participants()
    if not any(person.name == name for person in people):
        raise HTTPException(404, f"{name} não está no cadastro")

    updated = tuple(
        Participant(
            name=person.name,
            aliases=tuple(body.aliases) if body.aliases is not None else person.aliases,
            calorie_bonus=(
                body.calorie_bonus
                if body.calorie_bonus is not None
                else person.calorie_bonus
            ),
        )
        if person.name == name
        else person
        for person in people
    )
    services.repo.write_participants(updated)
    return participants_to_dict(services.repo.participants())
