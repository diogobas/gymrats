"""Previewing a month that is still a draft, and committing it.

Committing is the only write path in the system, so what it touches -- and
what it leaves alone -- is worth pinning down.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from gymrats.core import Entry, Modality, Period, Tables
from gymrats.storage.publisher import Publisher
from gymrats.storage.repository import Repository
from gymrats.storage.tally_service import TallyService

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def workspace(legacy_data, tmp_path):
    """A throwaway copy of the real data, safe to write to."""
    data = tmp_path / "data"
    assert legacy_data == data
    repo = Repository(data)
    return repo, TallyService(repo, Publisher(repo, tmp_path / "site"))


def july_tables() -> Tables:
    """A minimal, plausible July: two people, three scoring leaderboards."""
    raw = {}
    for modality, values in (
        (Modality.HUSTLE, {"Arthur": 300.0, "Diogo": 200.0}),
        (Modality.ACTIVE_DAYS, {"Arthur": 20.0, "Diogo": 18.0}),
        (Modality.CALORIES, {"Arthur": 9000.0, "Diogo": 8000.0}),
        (Modality.DISTANCE, {"Arthur": 50.0, "Diogo": 40.0}),
    ):
        raw[(modality, Period.MONTH)] = tuple(
            Entry(name=name, value=value, reported_position=position)
            for position, (name, value) in enumerate(values.items(), start=1)
        )
    return Tables.build(raw)


def test_a_preview_writes_nothing(workspace):
    repo, service = workspace
    before = sorted(path.name for path in (repo.root / "months").iterdir())

    preview = service.preview("2026-07", july_tables())

    assert [row.name for row in preview.month.standings] == ["Arthur", "Diogo"]
    assert sorted(path.name for path in (repo.root / "months").iterdir()) == before


def test_the_preview_season_already_counts_the_draft_month(workspace):
    """The point of previewing: seeing what the group will see."""
    _, service = workspace

    preview = service.preview("2026-07", july_tables())

    assert preview.season.months == tuple(f"2026-{n:02d}" for n in range(1, 8))
    arthur = next(row for row in preview.season.rows if row.name == "Arthur")
    assert arthur.by_month["2026-07"] == 1
    # Whoever sat July out takes last place plus one, as in any other month.
    isadora = next(row for row in preview.season.rows if row.name == "Isadora")
    assert isadora.by_month["2026-07"] == 3
    assert "2026-07" in isadora.imputed_months


def test_re_tallying_a_committed_month_replaces_it_instead_of_doubling_it(workspace):
    """Junho is already on disk. Previewing it again must not add a column."""
    _, service = workspace

    preview = service.preview("2026-06", july_tables())

    assert preview.season.months.count("2026-06") == 1
    assert len(preview.season.months) == 6


def test_committing_writes_the_month_and_republishes(workspace):
    repo, service = workspace

    result = service.commit("2026-07", july_tables())

    assert result.month_path == repo.month_path("2026-07")
    stored = json.loads(result.month_path.read_text(encoding="utf-8"))
    assert stored["month"] == "2026-07"
    assert stored["tables"]["hustle"]["month"][0] == {
        "name": "Arthur",
        "value": 300.0,
        "reported_position": 1,
    }

    published = {path.name for path in result.published}
    assert {"2026-06.json", "2026-07.json", "2026.json", "index.json"} <= published


def test_the_published_site_sees_the_new_month(workspace):
    _, service = workspace
    result = service.commit("2026-07", july_tables())

    index = next(path for path in result.published if path.name == "index.json")
    document = json.loads(index.read_text(encoding="utf-8"))

    assert document["latest_month"] == "2026-07"
    assert {"month": "2026-07", "year": 2026, "detail": True} in document["months"]


def test_committing_keeps_the_notes_the_admin_wrote_by_hand(workspace):
    """Those files are meant to be reopened and edited. Rewriting one from
    the API must not silently delete the comments in it."""
    repo, service = workspace
    before = json.loads(repo.month_path("2026-06").read_text(encoding="utf-8"))
    assert "_source" in before

    service.commit("2026-06", july_tables())

    after = json.loads(repo.month_path("2026-06").read_text(encoding="utf-8"))
    assert after["_source"] == before["_source"]
    assert [entry["name"] for entry in after["tables"]["hustle"]["month"]] == [
        "Arthur",
        "Diogo",
    ]
