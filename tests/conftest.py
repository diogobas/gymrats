from __future__ import annotations

import json
from pathlib import Path

import pytest

from gymrats.core import Entry, Modality, Period, Tables
from gymrats.storage.schema import participants_from_dict, tables_from_dict

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def participants():
    return participants_from_dict(load_fixture("participants.json"))


@pytest.fixture
def june_input():
    return load_fixture("2026-06.json")


@pytest.fixture
def june_tables(june_input):
    return tables_from_dict(june_input)


def make_tables(**by_modality) -> Tables:
    """Build a ``Tables`` from ``modality=[(name, value), ...]`` for unit tests.

    Pass ``modality_year=`` to populate the ``Period.YEAR`` slice.
    """
    raw: dict[tuple[Modality, Period], tuple[Entry, ...]] = {}
    for key, rows in by_modality.items():
        if key.endswith("_year"):
            modality, period = Modality(key[: -len("_year")]), Period.YEAR
        else:
            modality, period = Modality(key), Period.MONTH
        raw[(modality, period)] = tuple(
            Entry(name=name, value=float(value)) for name, value in rows
        )
    return Tables.build(raw)
