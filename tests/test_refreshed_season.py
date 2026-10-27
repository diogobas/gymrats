"""Reviewed January-September data and the exact public files it generates."""

from __future__ import annotations

import calendar
import json
from pathlib import Path

import pytest
from gymrats.core.models import Modality, Period
from gymrats.report import main as report_main
from gymrats.storage.publisher import Publisher
from gymrats.storage.repository import Repository
from gymrats.storage.tally_service import TallyService

ROOT = Path(__file__).resolve().parents[1]
REPO = Repository(ROOT / "data")
MONTHS = tuple(f"2026-{number:02d}" for number in range(1, 10))
EXPECTED = [
    (12, "Bruna"),
    (13, "Diogo"),
    (14, "Diogo"),
    (13, "Isadora"),
    (12, "Arthur"),
    (10, "Arthur"),
    (9, "Arthur"),
    (9, "Diogo"),
    (12, "Lorena"),
]


def test_all_nine_months_are_detailed_and_reachable():
    index = json.loads((ROOT / "frontend/public/data/index.json").read_text())
    assert REPO.months() == MONTHS
    assert index["latest_completed_month"] == "2026-09"
    assert [
        (m["month"], m["detail"]) for m in index["months"] if not m.get("provisional")
    ] == [(month, True) for month in MONTHS]
    for month, (count, winner) in zip(MONTHS, EXPECTED, strict=True):
        doc = json.loads((ROOT / f"frontend/public/data/months/{month}.json").read_text())
        assert doc["ranked_count"] == count
        assert doc["standings"][0]["name"] == winner
        assert doc["unresolved_ties"] == []
        assert all(row["values"]["duration_min"] is not None for row in doc["standings"])


@pytest.mark.parametrize("month", MONTHS)
def test_seven_rankings_have_matching_participants_and_explicit_dates(month):
    tables = REPO.tables(month)
    assert len(tables.data) == 7
    assert (
        len({frozenset(row.name for row in rows) for rows in tables.data.values()}) == 1
    )
    assert {len(rows) for rows in tables.data.values()} == {15}
    assert all(row.value >= 0 for rows in tables.data.values() for row in rows)
    assert set(tables.data) == {
        *((modality, Period.MONTH) for modality in Modality),
        (Modality.DISTANCE, Period.YEAR),
        (Modality.DURATION, Period.YEAR),
    }
    provenance = json.loads(REPO.month_path(month).read_text())["provenance"]
    last = f"{month}-{calendar.monthrange(2026, int(month[-2:]))[1]:02d}"
    assert provenance["source"] == "gymrats_api"
    assert provenance["monthly_start"] == month + "-01"
    assert provenance["monthly_end"] == provenance["annual_end"] == last
    assert provenance["annual_start"] == "2026-01-01"


def test_season_counts_each_reviewed_month_once():
    season = Publisher(REPO).season(2026, include_provisional=False)
    assert season.months == MONTHS
    assert [(row.name, row.total) for row in season.rows[:3]] == [
        ("Arthur", 21),
        ("Isadora", 24),
        ("Diogo", 33),
    ]
    assert all(row.total == sum(row.by_month.values()) for row in season.rows)
    assert season.unresolved_ties == ()
    june = TallyService(REPO).preview("2026-06", REPO.tables("2026-06"))
    assert june.season.months == MONTHS[:6]


def test_original_history_and_known_source_differences_are_preserved():
    review = json.loads((ROOT / "data/reviews/2026-api-refresh.json").read_text())
    original = REPO.history(2026)
    assert original["2026-01"][4] == "Thamyres"
    assert review["reviewed_on"] == "2026-10-27"
    assert "Admin approved" in review["decision"]
    for month in MONTHS[:5]:
        assert review["months"][month]["previous_order"] == original[month]
    for month in MONTHS[:4]:
        assert review["months"][month]["participants_missing_from_previous"] == [
            "Thamyres"
        ]
    assert (
        REPO.tables("2026-06").value_for("Lorrana", Modality.HUSTLE) == 217.68260607439217
    )
    assert any(
        item["name"] == "Lorrana"
        and item["metric"] == "hustle"
        and item["previous"] == 211.31
        for item in review["months"]["2026-06"]["previous_value_changes"]
    )


def test_report_defaults_to_latest_snapshot_and_respects_selected_cutoff(capsys):
    assert report_main(["--data", str(REPO.root)]) == 0
    latest = capsys.readouterr().out
    assert "CLASSIFICAÇÃO — 2026-10" in latest
    assert "PRÉVIA PROVISÓRIA" in latest
    assert "PONTOS CORRIDOS — 2026" in latest
    assert report_main(["--data", str(REPO.root), "--month", "2026-06"]) == 0
    june = capsys.readouterr().out
    assert "CLASSIFICAÇÃO — 2026-06" in june


def test_october_is_published_as_provisional_without_closing_it():
    assert "2026-10" not in REPO.months()
    assert REPO.provisional_months() == ("2026-10",)
    document = json.loads(REPO.provisional_path("2026-10").read_text())
    assert document["provisional"] is True
    assert document["provenance"]["monthly_end"] == "2026-10-26"
    assert len(REPO.public_tables("2026-10").data) == 7
    site = ROOT / "frontend/public/data"
    month = json.loads((site / "months/2026-10.json").read_text())
    season = json.loads((site / "season/2026.json").read_text())
    index = json.loads((site / "index.json").read_text())
    assert index["latest_month"] == "2026-10"
    assert index["months"][-1]["provisional"] is True
    assert month["provisional"] is season["provisional"] is True
    assert month["data_through"] == season["data_through"] == "2026-10-26"
    assert month["ranked_count"] == 9
    assert [r["name"] for r in month["standings"][:3]] == ["Diogo", "Lorena", "Arthur"]
    assert season["months"] == [*MONTHS, "2026-10"]
    assert [(r["name"], r["total"]) for r in season["standings"][:3]] == [
        ("Arthur", 24),
        ("Isadora", 33),
        ("Diogo", 34),
    ]
