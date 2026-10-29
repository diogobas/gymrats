"""The supplied CSVs restore former members and historical monthly results."""

import csv
import hashlib
import json
from pathlib import Path

import pytest
from gymrats.core import Modality, tally_month
from gymrats.storage.publisher import Publisher
from gymrats.storage.repository import Repository
from gymrats.storage.schema import month_result_to_dict, tables_from_dict

ROOT = Path(__file__).resolve().parents[1]
REPO = Repository(ROOT / "data")
MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-08"]


def canonical(name):
    return "Túlio" if name == "Tulio" else name


def csv_rows(path):
    with path.open(newline="", encoding="utf-8-sig") as source:
        return [row for row in list(csv.reader(source))[1:] if row and row[0].strip()]


@pytest.mark.parametrize("month", MONTHS)
def test_published_month_matches_all_four_supplied_csvs(month):
    source = json.loads(REPO.month_path(month).read_text())["official_result"]
    files = [ROOT / path for path in source["source_files"]]
    for path in files:
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest()
            == source["source_files"][str(path.relative_to(ROOT))]
        )
    final, hustle, days, calories = [csv_rows(path) for path in files]
    result = Publisher(REPO).month(month)
    assert result.ranked_count == len(final)
    for actual, expected in zip(result.standings, final, strict=True):
        rank, name, total, hustle_position, days_position, calorie_position = expected
        assert (actual.position, actual.name, actual.total) == (
            int(rank),
            canonical(name),
            int(total),
        )
        assert actual.positions == {
            Modality.HUSTLE: int(hustle_position),
            Modality.ACTIVE_DAYS: int(days_position),
            Modality.CALORIES: int(calorie_position),
        }
        assert actual.total == sum(actual.positions.values())
        assert actual.values[Modality.HUSTLE] is None
        assert actual.values[Modality.ACTIVE_DAYS] is None
        assert actual.values[Modality.DISTANCE] is None
        assert actual.values[Modality.DURATION] is None
    by_name = {r.name: r for r in result.standings}
    for modality, rows in [(Modality.HUSTLE, hustle), (Modality.ACTIVE_DAYS, days)]:
        for name, position in rows:
            assert by_name[canonical(name)].positions[modality] == int(position)
    for row in calories:
        assert by_name[canonical(row[0])].positions[Modality.CALORIES] == int(row[1])
        assert by_name[canonical(row[0])].calories_adjusted == float(row[3])
        assert by_name[canonical(row[6])].values[Modality.CALORIES] == float(row[8])
    public = month_result_to_dict(result, "test")
    assert public["official_source"] == source["source_url"]
    assert all("duration" not in r["positions"] for r in public["standings"])


def test_thamyres_returns_to_the_season_and_absences_use_official_field_sizes():
    season = Publisher(REPO).season(2026, include_provisional=False)
    rows = {r.name: r for r in season.rows}
    assert len(rows) == 15
    assert [rows["Thamyres"].by_month[m] for m in MONTHS[:4]] == [5, 5, 6, 10]
    assert not set(MONTHS[:4]).intersection(rows["Thamyres"].imputed_months)
    assert rows["Thamyres"].by_month["2026-05"] == 12
    assert rows["Thamyres"].total == 82
    assert rows["Thamyres"].imputed_months == tuple(f"2026-{n:02d}" for n in range(5, 10))
    assert rows["Lorena"].by_month["2026-01"] == 14
    assert rows["Nathane"].by_month["2026-02"] == 15
    assert rows["Lorrana"].by_month["2026-03"] == 14
    assert rows["Paula"].by_month["2026-03"] == 14
    preview = Publisher(REPO).season(2026)
    thamyres = next(r for r in preview.rows if r.name == "Thamyres")
    assert thamyres.by_month["2026-10"] == 10
    assert "2026-10" in thamyres.imputed_months


def test_accumulated_totals_and_order_match_the_corrected_official_sheet():
    season = Publisher(REPO).season(2026, include_provisional=False)
    expected = [
        ("Arthur", 24),
        ("Isadora", 24),
        ("Diogo", 32),
        ("Bruna", 37),
        ("Andressa", 57),
        ("Lorena", 59),
        ("Túlio", 69),
        ("Laíssa", 77),
        ("Thamyres", 82),
        ("William", 87),
        ("Lorrana", 89),
        ("João", 90),
        ("Nathane", 90),
        ("Paula", 103),
        ("Ricardo", 108),
    ]
    assert [(r.name, r.total) for r in season.rows] == expected
    assert [r.position for r in season.rows] == list(range(1, 16))
    assert all(r.total == sum(r.by_month.values()) for r in season.rows)


def test_incomplete_current_api_does_not_recompute_official_2026():
    doc = json.loads(REPO.month_path("2026-01").read_text())
    doc["tables"] = {}
    assert tally_month("2026-01", tables_from_dict(doc)).position_of("Thamyres") == 5


@pytest.mark.parametrize("change", ["missing", "mixed", "extra"])
def test_official_months_require_consistent_supported_scoring_columns(change):
    doc = json.loads(REPO.month_path("2026-01").read_text())
    row = doc["official_result"]["standings"][0]
    if change == "missing":
        row["positions"].pop("calories")
    elif change == "mixed":
        row["positions"]["duration"] = 1
    else:
        row["positions"]["distance"] = 1
    row["total"] = sum(row["positions"].values())
    with pytest.raises(ValueError, match="official"):
        tables_from_dict(doc)
