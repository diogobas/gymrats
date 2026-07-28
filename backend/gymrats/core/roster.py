"""Resolving a scraped name to a registered participant.

GymRats prints the full profile name ("Andressa Barcelos Aires Barros") while
the tally uses the short one ("Andressa"). Aliases bridge that.

An unknown name is NEVER guessed. ``resolve`` returns ``None`` and the review
screen asks which person it is, or offers to register a new one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import Participant
from .values import normalize_name

__all__ = ["Roster", "NameResolution"]


@dataclass(frozen=True)
class NameResolution:
    scraped: str
    canonical: str | None
    matched_on: str | None  # "name" | "alias" | "normalized" | None


class Roster:
    def __init__(self, participants: Iterable[Participant]):
        self.participants = tuple(participants)
        self._by_name = {person.name: person for person in self.participants}
        self._by_alias: dict[str, Participant] = {}
        self._by_normalized: dict[str, Participant] = {}
        for person in self.participants:
            for label in (person.name, *person.aliases):
                self._by_alias.setdefault(label, person)
                self._by_normalized.setdefault(normalize_name(label), person)

    def __iter__(self):
        return iter(self.participants)

    def get(self, name: str) -> Participant | None:
        return self._by_name.get(name)

    def resolve(self, scraped: str) -> NameResolution:
        """Exact name, then alias, then accent- and case-insensitive match.

        The normalized pass is what absorbs OCR dropping the accent on "Túlio"
        or "Laíssa". Anything past that is a decision for the admin.
        """
        if scraped in self._by_name:
            return NameResolution(scraped, scraped, "name")
        person = self._by_alias.get(scraped)
        if person is not None:
            return NameResolution(scraped, person.name, "alias")
        person = self._by_normalized.get(normalize_name(scraped))
        if person is not None:
            return NameResolution(scraped, person.name, "normalized")
        return NameResolution(scraped, None, None)
