"""What the static site is handed.

The site has no backend and no logic of its own: whatever it cannot find in
these files, it cannot show. So the assertions here are about completeness --
every month reachable, every tie explained, every accent intact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import write_legacy_data
from gymrats.publish import main as publish_main
from gymrats.storage.publisher import Publisher
from gymrats.storage.repository import Repository

DATA = Path(__file__).resolve().parents[1] / "data"
GENERATED_AT = "2026-07-02T21:15:03-03:00"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """The real data/, published into a throwaway directory."""
    out = tmp_path_factory.mktemp("site")
    legacy = write_legacy_data(tmp_path_factory.mktemp("legacy"))
    Publisher(Repository(legacy), out).publish(generated_at=GENERATED_AT)
    return out


def read(site: Path, *parts: str) -> dict:
    return json.loads((site.joinpath(*parts)).read_text(encoding="utf-8"))


# -- the manifest ----------------------------------------------------------


def test_the_index_lists_every_month_of_the_season(site):
    index = read(site, "index.json")

    assert [item["month"] for item in index["months"]] == [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
    ]
    assert index["latest_month"] == "2026-06"
    assert index["years"] == [2026]


def test_history_months_are_marked_as_having_no_detail(site):
    """January has no leaderboards, only a finishing order. Say so up front.

    Otherwise the site fetches months/2026-01.json, gets a 404 and has to
    guess whether that means "hand-tallied" or "publish is broken".
    """
    index = read(site, "index.json")
    detail = {item["month"]: item["detail"] for item in index["months"]}

    assert detail["2026-01"] is False
    assert detail["2026-06"] is True
    assert not (site / "months" / "2026-01.json").exists()


def test_a_month_without_its_own_file_is_still_readable_from_the_season(site):
    """The order of a history month comes from the season columns."""
    season = read(site, "season", "2026.json")
    january = {row["name"]: row["by_month"]["2026-01"] for row in season["standings"]}

    assert january["Bruna"] == 1
    assert january["Isadora"] == 2
    # Nathane joined in February; January is imputed, not competed.
    nathane = next(row for row in season["standings"] if row["name"] == "Nathane")
    assert "2026-01" in nathane["imputed_months"]


# -- the month document ----------------------------------------------------


def test_june_is_published_in_finishing_order(site):
    june = read(site, "months", "2026-06.json")

    assert [row["name"] for row in june["standings"][:4]] == [
        "Arthur",
        "Andressa",
        "Isadora",
        "Diogo",
    ]
    assert june["generated_at"] == GENERATED_AT
    assert june["ranked_count"] == 10


def test_every_tie_carries_the_sentence_that_explains_it(site):
    """The point of the whole thing: the result justifies itself.

    A tiebreak with no readable detail means the admin has to explain the
    table in the group chat, which is exactly what the site exists to avoid.
    """
    june = read(site, "months", "2026-06.json")
    season = read(site, "season", "2026.json")

    tiebreaks = [
        row["tiebreak"]
        for row in june["standings"] + season["standings"]
        if row["tiebreak"] is not None
    ]
    assert tiebreaks
    for info in tiebreaks:
        assert info["detail"].startswith("Empate em ")
        assert info["tied_with"]

    arthur = june["standings"][0]
    assert arthur["tiebreak"]["detail"] == (
        "Empate em 4 pontos com Andressa. "
        "Desempatado por maior distância no mês: Arthur 107,33 km, Andressa 5,64 km."
    )


def test_the_calorie_bonus_is_legible_from_the_published_row(site):
    """Marking the row is not enough -- the raw figure has to travel too.

    Six of June's ten places moved because of the bonus. Someone comparing the
    site against their own app screen needs to see both numbers.
    """
    june = read(site, "months", "2026-06.json")
    andressa = next(row for row in june["standings"] if row["name"] == "Andressa")

    assert andressa["values"]["calories"]["raw"] == 10593.0
    assert andressa["values"]["calories"]["bonus_applied"] is True
    assert andressa["values"]["calories"]["adjusted"] == 12711.6


# -- the season document ---------------------------------------------------


def test_the_season_totals_match_the_admin_sheet(site):
    season = read(site, "season", "2026.json")

    assert season["months"] == [f"2026-{n:02d}" for n in range(1, 7)]
    assert [row["name"] for row in season["standings"][:3]] == [
        "Isadora",
        "Diogo",
        "Arthur",
    ]
    assert [row["total"] for row in season["standings"][:3]] == [15, 16, 16]


def test_the_season_tiebreak_is_the_year_snapshot_not_a_sum_of_months(site):
    """Diogo and Arthur both finish on 16; the year's distance separates them."""
    season = read(site, "season", "2026.json")
    diogo = next(row for row in season["standings"] if row["name"] == "Diogo")

    assert diogo["tiebreak"]["resolved_by"] == "distance"
    assert diogo["tiebreak"]["comparison"] == {"Diogo": 1026.13, "Arthur": 893.06}


# -- the files themselves --------------------------------------------------


def test_accents_survive_the_round_trip(site):
    """Túlio and Laíssa are written as themselves, not as \\u00fa escapes.

    These files get committed and read in diffs.
    """
    raw = (site / "months" / "2026-06.json").read_text(encoding="utf-8")

    assert "Túlio" in raw
    assert "distância" in raw
    assert "\\u" not in raw


def test_publishing_twice_writes_the_same_bytes(site, tmp_path):
    """Nothing about publishing depends on when it ran, except the stamp."""
    again = tmp_path / "again"
    legacy = write_legacy_data(tmp_path / "legacy")
    Publisher(Repository(legacy), again).publish(generated_at=GENERATED_AT)

    for path in sorted(site.rglob("*.json")):
        assert path.read_bytes() == (again / path.relative_to(site)).read_bytes()


def test_the_committed_site_data_matches_the_tally(tmp_path):
    """frontend/public/data/ is generated, committed, and easy to forget.

    Nothing else reads those files, so a rule change published nowhere would
    leave the site serving last month's standings without a single failure.
    Only the timestamp is allowed to differ, so it is pinned to the committed
    one before comparing.
    """
    site = Path(__file__).resolve().parents[1] / "frontend" / "public" / "data"
    if not site.is_dir():
        pytest.skip("o site ainda não foi publicado")

    committed = json.loads((site / "index.json").read_text(encoding="utf-8"))
    Publisher(Repository(DATA), tmp_path).publish(generated_at=committed["generated_at"])

    expected = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*.json"))
    published = sorted(path.relative_to(site) for path in site.rglob("*.json"))
    assert published == expected, "rode: uv run python -m gymrats.publish"

    for relative in expected:
        assert (site / relative).read_text(encoding="utf-8") == (
            tmp_path / relative
        ).read_text(encoding="utf-8"), f"{relative} desatualizado — rode o publish"


def test_the_cli_writes_where_it_is_told(legacy_data, tmp_path, capsys):
    out = tmp_path / "public" / "data"

    assert publish_main(["--data", str(legacy_data), "--out", str(out)]) == 0
    assert (out / "index.json").is_file()
    assert (out / "months" / "2026-06.json").is_file()
    assert (out / "season" / "2026.json").is_file()
    assert "3 arquivos" in capsys.readouterr().out


def test_the_cli_refuses_an_empty_data_directory(tmp_path):
    with pytest.raises(SystemExit):
        publish_main(["--data", str(tmp_path), "--out", str(tmp_path / "out")])
