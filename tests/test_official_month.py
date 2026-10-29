"""Historical standings survive publication without applying today's rules."""

import copy
import json
from pathlib import Path

import pytest
from gymrats.core.models import Modality
from gymrats.core.scoring import tally_month
from gymrats.report import print_month
from gymrats.storage.publisher import Publisher
from gymrats.storage.repository import Repository
from gymrats.storage.schema import month_result_to_dict, tables_from_dict
from gymrats.storage.tally_service import TallyService

ROOT = Path(__file__).resolve().parents[1]
REPO = Repository(ROOT / "data")


def test_official_january_preserves_all_positions_and_historical_points(capsys):
    result = Publisher(REPO).month("2025-01")
    assert result.ranked_count == 22
    assert [r.name for r in result.standings[:4]] == [
        "Ludimilla",
        "Isadora",
        "Arthur",
        "Roberto Alexandre",
    ]
    assert result.position_of("Túlio") == 15
    assert result.position_of("Vitão") == 20
    assert result.position_of("Diogo") == 7
    assert result.position_of("Lorrana") == 8
    assert all(r.total == sum(r.positions.values()) for r in result.standings)
    doc = month_result_to_dict(result, "test")
    assert doc["official_source"].endswith("gid=1062005162")
    assert doc["standings"][0]["positions"]["duration"] == 1
    assert doc["standings"][0]["values"]["hustle"] is None
    assert doc["standings"][0]["values"]["calories"]["raw"] == 18436
    print_month(result)
    assert "duração" in capsys.readouterr().out


def test_official_january_is_used_by_season_and_subsequent_previews():
    season = Publisher(REPO).season(2025)
    rows = {row.name: row for row in season.rows}
    assert rows["Bruna"].by_month["2025-01"] == 23
    assert rows["Jorge Luiz"].by_month["2025-01"] == 23
    assert rows["Thamyres"].by_month["2025-01"] == 23
    assert rows["Isadora"].by_month["2025-01"] == 2
    assert "2025-01" not in rows["Isadora"].imputed_months
    preview = TallyService(REPO).preview("2025-02", REPO.tables("2025-02"))
    assert (
        next(r for r in preview.season.rows if r.name == "Túlio").by_month["2025-01"]
        == 15
    )


def test_incomplete_api_values_cannot_overwrite_official_standings():
    doc = json.loads(REPO.month_path("2025-01").read_text())
    doc["tables"]["hustle"]["month"] = []
    tables = tables_from_dict(doc)
    assert tally_month("2025-01", tables).position_of("Isadora") == 2
    assert tables.official_result.standings[0].values[Modality.HUSTLE] is None
    with pytest.raises(ValueError, match="month differs"):
        tally_month("2025-02", tables)


@pytest.mark.parametrize("change", ["sum", "duplicate", "position", "source"])
def test_invalid_official_results_are_rejected(change):
    doc = json.loads(REPO.month_path("2025-01").read_text())
    official = copy.deepcopy(doc["official_result"])
    if change == "sum":
        official["standings"][0]["total"] = 3
    elif change == "duplicate":
        official["standings"][1]["name"] = official["standings"][0]["name"]
    elif change == "position":
        official["standings"][14]["position"] = 12
    else:
        official.pop("source_url")
    doc["official_result"] = official
    with pytest.raises(ValueError, match=r"official|Official"):
        tables_from_dict(doc)
