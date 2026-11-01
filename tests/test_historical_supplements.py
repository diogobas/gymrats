"""API values stay authoritative; missing historical measurements stay unknown."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import make_tables
from gymrats.core.models import (
    Modality,
    MonthResult,
    Period,
    Tables,
)
from gymrats.core.scoring import tally_month
from gymrats.core.season import build_season
from gymrats.core.supplements import insert_position
from gymrats.core.tiebreak import break_tie
from gymrats.report import main as report_main
from gymrats.storage.publisher import Publisher
from gymrats.storage.repository import Repository
from gymrats.storage.schema import month_result_to_dict, tables_from_dict

ROOT = Path(__file__).resolve().parents[1]
REPO = Repository(ROOT / "data")
REPORT = json.loads((ROOT / "data/reviews/2026-api-with-thamyres.json").read_text())


@pytest.mark.parametrize("month", REPORT["months"])
def test_api_source_is_unchanged_and_spreadsheet_override_is_archived(month):
    document = json.loads(REPO.month_path(month).read_text())
    assert "official_result" not in document
    assert document["_archived_official_result"]["source_files"]
    assert (
        hashlib.sha256(
            json.dumps(document["tables"], sort_keys=True).encode()
        ).hexdigest()
        == REPORT["months"][month]["api_tables_sha256"]
    )
    tables = REPO.tables(month)
    result = Publisher(REPO).month(month)
    assert result.source_url is None
    assert [
        {"name": row.name, "position": row.position, "total": row.total}
        for row in result.standings
    ] == REPORT["months"][month]["after"]
    if month in ("2026-05", "2026-08"):
        assert not tables.supplements
        assert result == tally_month(
            month, Tables.build(tables.data), REPO.participants()
        )
    for row in result.standings:
        assert row.total == sum(row.positions.values())
        if row.name == "Thamyres":
            continue
        for metric in Modality:
            assert row.values[metric] == tables.value_for(row.name, metric)


@pytest.mark.parametrize(
    ("month", "days", "hustle_rank", "days_rank"),
    [
        ("2026-01", 27, 4, 1),
        ("2026-02", 22, 3, 3),
        ("2026-03", 24, 5, 4),
        ("2026-04", None, 10, 9),
    ],
)
def test_thamyres_has_only_supported_values(month, days, hustle_rank, days_rank):
    result = Publisher(REPO).month(month)
    row = next(item for item in result.standings if item.name == "Thamyres")
    assert row.values[Modality.HUSTLE] is None
    assert row.values[Modality.ACTIVE_DAYS] == days
    assert row.positions[Modality.HUSTLE] == hustle_rank
    assert row.positions[Modality.ACTIVE_DAYS] == days_rank
    assert row.values[Modality.DISTANCE] is None
    assert row.values[Modality.DURATION] is None
    assert row.calories_adjusted == pytest.approx(row.values[Modality.CALORIES] * 1.2)
    public = month_result_to_dict(result, "test")
    assert public["historical_supplements"][0]["name"] == "Thamyres"


def test_inferred_days_match_api_values_for_historically_tied_people():
    for month in ("2026-01", "2026-02", "2026-03"):
        evidence = REPORT["months"][month]["active_days_evidence"]
        assert evidence["method"] == "equal_historical_rank"
        for peer in evidence["peers"]:
            assert (
                REPO.tables(month).value_for(peer, Modality.ACTIVE_DAYS)
                == evidence["value"]
            )
    assert REPORT["months"]["2026-04"]["active_days_evidence"]["range"] == [15, 19]


def test_position_insertion_counts_person_and_preserves_existing_ties():
    positions = {"A": 1, "B": 1, "C": 3, "D": 4}
    insert_position(positions, "Missing", 3)
    assert positions == {"A": 1, "B": 1, "Missing": 3, "C": 4, "D": 5}
    with pytest.raises(ValueError, match="split a tie"):
        insert_position({"A": 1, "B": 1}, "Missing", 2)


def test_unknown_distance_does_not_fabricate_a_tiebreak_loss():
    result = Publisher(REPO).month("2026-03")
    assert result.unresolved_ties == (("João", "Thamyres"),)
    rows = {row.name: row for row in result.standings}
    assert rows["João"].position == rows["Thamyres"].position == 6
    assert rows["Thamyres"].tiebreak.resolved_by is None
    assert rows["Andressa"].position == 8
    # Normal missing API entries keep their established behavior.
    tables = make_tables(distance=[("A", 100)])
    assert break_tie(["A", "Thamyres"], tables, Period.MONTH).blocks == (
        ("A",),
        ("Thamyres",),
    )
    marked = replace(tables, supplements=REPO.tables("2026-03").supplements)
    assert break_tie(["A", "Thamyres"], marked, Period.MONTH).unresolved == (
        ("A", "Thamyres"),
    )


def test_annual_tiebreak_also_preserves_unknown_historical_measurements():
    original = Publisher(REPO).month("2026-01")
    rows = {row.name: row for row in original.standings}
    tied = MonthResult(
        month="2026-01",
        standings=(
            replace(rows["Arthur"], position=1),
            replace(rows["Thamyres"], position=1),
        ),
        supplements=original.supplements,
    )
    annual = Tables.build(
        {
            (Modality.DISTANCE, Period.YEAR): REPO.tables("2026-10").get(
                Modality.DISTANCE, Period.YEAR
            )
        }
    )
    season = build_season(2026, [tied], annual)
    assert season.unresolved_ties == (("Arthur", "Thamyres"),)


def test_supplement_cannot_duplicate_an_api_participant_or_split_a_tie():
    tables = REPO.tables("2026-01")
    item = tables.supplements[0]
    with pytest.raises(ValueError, match="already in API"):
        tally_month(
            "2026-01",
            replace(tables, supplements=(replace(item, name="Diogo"),)),
            REPO.participants(),
        )
    bad = replace(item, values={**item.values, Modality.ACTIVE_DAYS: 1})
    with pytest.raises(ValueError, match="historical position"):
        tally_month("2026-01", replace(tables, supplements=(bad,)), REPO.participants())


def test_sparse_historical_values_survive_roundtrip_and_render_in_report(
    tmp_path, capsys
):
    repo = Repository(tmp_path / "data")
    original = REPO.tables("2026-04")
    path = repo.write_tables("2026-04", original)
    assert tables_from_dict(json.loads(path.read_text())) == original
    assert report_main(["--data", str(REPO.root), "--month", "2026-04"]) == 0
    line = next(
        line for line in capsys.readouterr().out.splitlines() if "Thamyres" in line
    )
    assert line.count("-") >= 3
