"""2024 groups have separate sources, scoring and season coverage."""

import json
from pathlib import Path

from gymrats.core.models import Modality
from gymrats.core.scoring import tally_month
from gymrats.storage.publisher import Publisher
from gymrats.storage.repository import Repository
from gymrats.storage.schema import month_result_to_dict
from gymrats.storage.tally_service import TallyService

ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = Publisher(Repository(ROOT / "data"))
WOMEN = Publisher(Repository(ROOT / "data/categories/2024-women"))


def test_female_months_preserve_the_source_including_tie_order():
    snapshot = json.loads(
        (ROOT / "data/sources/2024-women/spreadsheets.json").read_text()
    )
    months = {
        "Agosto 2024": "2024-08",
        "Setembro 2024": "2024-09",
        "Outubro 2024": "2024-10",
        "GIRLS Novembro 2024": "2024-11",
    }
    for source in snapshot["sources"]:
        for sheet in source["ranges"]:
            if sheet["properties"]["title"] not in months:
                continue
            month = months[sheet["properties"]["title"]]
            expected = []
            for cells in sheet["data"][0]["rows"][1:]:
                values = [cell["value"] for cell in cells]
                if len(values) < 7 or not values[0]:
                    continue
                name = {"Laura": "Laura Beatriz"}.get(values[1], values[1])
                expected.append((int(values[0]), name, int(values[2])))
            result = WOMEN.month(month)
            assert [(r.position, r.name, r.total) for r in result.standings] == expected
            assert all(r.total == sum(r.positions.values()) for r in result.standings)
            doc = month_result_to_dict(result, "test")
            assert all(r["values"]["calories"]["raw"] is None for r in doc["standings"])
            assert all(r["positions"]["duration"] for r in doc["standings"])


def test_female_season_has_no_july_or_december_and_keeps_unresolved_ties():
    result = WOMEN.season(2024)
    assert result.months == ("2024-08", "2024-09", "2024-10", "2024-11")
    rows = {row.name: row for row in result.rows}
    assert [(r.name, r.total) for r in result.rows[:3]] == [
        ("Ludimilla", 7),
        ("Lorena", 13),
        ("Isadora", 15),
    ]
    assert rows["Lorena"].by_month["2024-09"] == 10
    assert rows["Lorena"].imputed_months == ("2024-09",)
    assert rows["Amanda"].position == rows["Laiury"].position == 9
    assert {"Amanda", "Laiury"} in [set(group) for group in result.unresolved_ties]
    assert all(set(r.by_month) == set(result.months) for r in result.rows)


def test_male_ranks_are_recalculated_before_scoring_without_changing_raw_api():
    for month in ("2024-11", "2024-12"):
        raw = PUBLISHER.repo.tables(month)
        assert "Nathane" in raw.names(Modality.HUSTLE)
        scoped = PUBLISHER.scoped_tables(month)
        assert "Nathane" not in scoped.names(Modality.HUSTLE)
        result = PUBLISHER.month(month)
        assert result == tally_month(month, scoped, PUBLISHER.repo.participants())
        assert not (
            {r.name for r in result.standings} & {r.name for r in WOMEN.season(2024).rows}
        )
    assert PUBLISHER.season(2024).months == tuple(f"2024-{m:02d}" for m in range(5, 13))
    assert PUBLISHER.month("2025-01").position_of("Isadora") == 2


def test_category_manifest_points_only_to_published_womens_months(tmp_path):
    PUBLISHER.__class__(PUBLISHER.repo, tmp_path).publish(generated_at="test")
    index = json.loads((tmp_path / "index.json").read_text())
    (category,) = index["categories"]
    assert category["year"] == 2024
    assert category["months"] == list(WOMEN.repo.months())
    path = tmp_path / category["path"]
    assert not (path / "months/2024-12.json").exists()
    season = json.loads((path / "season/2024.json").read_text())
    assert "dezembro" in season["coverage_note"]
    assert season["standings"][0]["name"] == "Ludimilla"


def test_admin_preview_and_report_use_the_same_male_scope(capsys):
    from gymrats.report import main

    preview = TallyService(PUBLISHER.repo).preview(
        "2024-12", PUBLISHER.repo.tables("2024-12")
    )
    assert preview.month == PUBLISHER.month("2024-12")
    assert preview.season == PUBLISHER.season(2024)
    assert main(["--data", str(ROOT / "data"), "--month", "2024-12"]) == 0
    output = capsys.readouterr().out
    assert "Andressa" not in output
    assert "Nathane" not in output
