"""The official monthly results and 20-person season, including historical exceptions."""

import hashlib
import json
from pathlib import Path

import pytest
from gymrats.core import Modality
from gymrats.report import main as report_main
from gymrats.storage.publisher import Publisher
from gymrats.storage.repository import Repository
from gymrats.storage.tally_service import TallyService

ROOT = Path(__file__).resolve().parents[1]
REPO = Repository(ROOT / "data")
SNAPSHOT = ROOT / "data/sources/2025-official/spreadsheet.json"
SOURCE = json.loads(SNAPSHOT.read_text())
TABS = {tab["properties"]["title"]: tab for tab in SOURCE["sheets"]}
LABELS = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]
ALIASES = {
    "Tulio": "Túlio",
    "Betin": "Roberto Alexandre",
    "Jéssica": "Jéssica Felter",
    "Heitor": "Heitor Rocha",
    "Vitor": "Vitão",
    "Gustavo": "Gustavo Calabresi",
    "Jorge": "Jorge Luiz",
    "Nyelsen": "Nyelsen Soares Costa",
    "Bruno": "Bruno Bandeira",
    "Diego": "Diego Antunes",
}


def canonical(name):
    return ALIASES.get(name, name)


@pytest.mark.parametrize(("number", "label"), list(enumerate(LABELS, 1)))
def test_every_month_preserves_official_positions_totals_and_historical_values(
    number, label
):
    month = f"2025-{number:02d}"
    official = json.loads(REPO.month_path(month).read_text())["official_result"]
    assert (
        official["source_files"][str(SNAPSHOT.relative_to(ROOT))]
        == hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
    )
    expected = TABS[f"{label} 2025"]["values"][1:]
    actual = Publisher(REPO).month(month)
    assert actual.source_url.endswith(
        f"gid={TABS[f'{label} 2025']['properties']['sheetId']}"
    )
    modalities = [Modality.HUSTLE, Modality.ACTIVE_DAYS]
    if number <= 9:
        modalities.append(Modality.DURATION)
    modalities.append(Modality.CALORIES)
    calories = TABS[f"Calories {label}/25"]["values"][1:]
    raw_name_column = 7 if number == 1 else 6
    raw = {
        canonical(r[raw_name_column]): r[8]
        for r in calories
        if len(r) > 8 and isinstance(r[raw_name_column], str)
    }
    adjusted = {
        canonical(r[0]): r[2 if number == 1 else 3]
        for r in calories
        if len(r) > 1 and isinstance(r[0], str)
    }
    for row, source in zip(actual.standings, expected, strict=True):
        position, name, total, *parts = source
        name = canonical(name)
        assert (row.position, row.name, row.total) == (position, name, total)
        assert row.positions == dict(zip(modalities, parts, strict=True))
        assert row.total == sum(row.positions.values())
        assert row.values[Modality.CALORIES] == raw[name]
        assert row.calories_adjusted == adjusted[name]
        assert row.values[Modality.HUSTLE] is None
        assert row.values[Modality.ACTIVE_DAYS] is None
        assert row.values[Modality.DURATION] is None
        assert row.values[Modality.DISTANCE] is None


def test_all_240_monthly_scores_and_20_totals_match_the_official_accumulated_sheet():
    expected = TABS["Pontos Corridos 2025"]["values"][1:]
    season = Publisher(REPO).season(2025)
    by_name = {row.name: row for row in season.rows}
    assert set(by_name) == {canonical(row[1]) for row in expected}
    assert len(by_name) == 20
    for _, name, total, *scores in expected:
        row = by_name[canonical(name)]
        assert list(row.by_month.values()) == scores
        assert row.total == total == sum(scores)
    assert [r.total for r in season.rows] == sorted(row[2] for row in expected)
    assert [r.position for r in season.rows] == list(range(1, 21))
    assert by_name["Thamyres"].position < by_name["Jorge Luiz"].position
    assert by_name["Jorge Luiz"].position == 13
    assert season.absence_overrides == {"2025-08": 18, "2025-12": 13}


@pytest.mark.parametrize("month", ["2025-02", "2025-08", "2025-12"])
def test_admin_previews_use_the_same_season_scope_and_historical_absence_scores(month):
    preview = TallyService(REPO).preview(month, REPO.tables(month))
    expected = TABS["Pontos Corridos 2025"]["values"][1:]
    by_name = {r.name: r for r in preview.season.rows}
    assert len(by_name) == 20
    for source in expected:
        scores = source[3 : 3 + int(month[-2:])]
        actual = by_name[canonical(source[1])]
        assert list(actual.by_month.values()) == scores
        assert actual.total == sum(scores)
    assert max(preview.season.months) == month
    assert all(m <= month for m in preview.season.absence_overrides)


def test_monthly_participants_are_preserved_outside_the_season_scope():
    publisher = Publisher(REPO)
    assert publisher.month("2025-01").position_of("Ludimilla") == 1
    assert publisher.month("2025-06").position_of("Geovana") == 3
    assert "Ludimilla" not in {r.name for r in publisher.season(2025).rows}
    assert publisher.month("2025-07").position_of("Thamyres") == 5


@pytest.mark.parametrize("month", ["2025-02", "2025-12"])
def test_report_handles_both_three_and_four_official_scoring_columns(month, capsys):
    assert report_main(["--data", str(REPO.root), "--month", month]) == 0
    output = capsys.readouterr().out
    assert "Classificação oficial" in output
    assert "pontuação por ausência registrada na planilha oficial" in output


@pytest.mark.parametrize("change", ["year", "source", "duplicate", "month", "score"])
def test_invalid_historical_season_rules_are_rejected(tmp_path, change):
    doc = json.loads((ROOT / "data/seasons/2025.json").read_text())
    if change == "year":
        doc["year"] = 2026
    elif change == "source":
        doc.pop("source_url")
    elif change == "duplicate":
        doc["eligible_names"].append(doc["eligible_names"][0])
    elif change == "month":
        doc["absentee_scores"]["2026-01"] = 13
    else:
        doc["absentee_scores"]["2025-08"] = True
    directory = tmp_path / "seasons"
    directory.mkdir()
    (directory / "2025.json").write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="season"):
        Repository(tmp_path).season_options(2025)
