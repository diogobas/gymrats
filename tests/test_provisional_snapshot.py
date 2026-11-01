"""Provisional snapshots publish clearly and never turn into a closed month."""

import json
from pathlib import Path

import pytest
from gymrats.storage.publisher import Publisher
from gymrats.storage.repository import Repository
from gymrats.storage.tally_service import TallyService


def provenance(end="2026-07-26"):
    return dict(
        source="gymrats_api",
        monthly_start="2026-07-01",
        monthly_end=end,
        annual_start="2026-01-01",
        annual_end=end,
    )


def test_snapshot_is_separate_and_later_closed_data_takes_precedence(
    legacy_data, tmp_path
):
    repo = Repository(legacy_data)
    publisher = Publisher(repo, tmp_path / "site")
    tally = TallyService(repo, publisher)
    tables = repo.tables("2026-06")
    before = Publisher(repo).season(2026)
    tally.commit("2026-07", tables, provenance=provenance(), provisional=True)
    assert repo.months() == ("2026-06",)
    assert repo.provisional_months() == ("2026-07",)
    assert Publisher(repo).season(2026, include_provisional=False) == before
    assert Publisher(repo).season(2026) == before
    assert Publisher(repo).season(2026, include_provisional=True).months[-1] == "2026-07"
    season = json.loads((publisher.out_dir / "season/2026.json").read_text())
    assert season["closed_only"] is True
    assert "provisional" not in season
    assert season["data_through"] == "2026-06-30"
    assert "2026-07" not in season["months"]
    # Closing uses a new complete collection; the old preview remains audit data.
    tally.commit("2026-07", tables, provenance=provenance("2026-07-31"))
    assert repo.provisional_path("2026-07").is_file()
    assert repo.provisional_months() == ()
    index = json.loads((publisher.out_dir / "index.json").read_text())
    assert index["latest_completed_month"] == "2026-07"
    assert "provisional" not in index["months"][-1]
    season = json.loads((publisher.out_dir / "season/2026.json").read_text())
    assert "provisional" not in season
    assert season["months"].count("2026-07") == 1
    with pytest.raises(ValueError, match="closed month"):
        tally.commit("2026-07", tables, provenance=provenance(), provisional=True)


def test_previews_do_not_change_official_totals_membership_or_tiebreaks(
    legacy_data, tmp_path
):
    from gymrats.core.models import Entry, Modality, Participant, Period, Tables

    repo = Repository(legacy_data)
    repo.write_participants([*repo.participants(), Participant("Visitante")])
    publisher = Publisher(repo, tmp_path / "site")
    publisher.publish()
    before = publisher.season(2026)
    before_doc = json.loads((publisher.out_dir / "season/2026.json").read_text())
    before_doc.pop("generated_at")
    original = repo.tables("2026-06")
    changed = dict(original.data)
    for key, rows in changed.items():
        changed[key] = (*rows, Entry("Visitante", 100000))
    # Reverse the annual distance advantage in the unclosed month.
    changed[(Modality.DISTANCE, Period.YEAR)] = tuple(
        Entry(row.name, 1000000 if row.name == "Arthur" else 0)
        for row in changed[(Modality.DISTANCE, Period.YEAR)]
    )
    tables = Tables.build(changed)
    tally = TallyService(repo, publisher)
    for cutoff in ("2026-07-26", "2026-07-27"):
        tally.commit("2026-07", tables, provenance=provenance(cutoff), provisional=True)
        assert publisher.season(2026) == before
        document = json.loads((publisher.out_dir / "season/2026.json").read_text())
        document.pop("generated_at")
        assert document == before_doc
        assert "Visitante" not in {row["name"] for row in document["standings"]}
        month = json.loads((publisher.out_dir / "months/2026-07.json").read_text())
        assert month["provisional"] is True
        assert "Visitante" in {row["name"] for row in month["standings"]}
    tally.commit("2026-07", tables, provenance=provenance("2026-07-31"))
    season = json.loads((publisher.out_dir / "season/2026.json").read_text())
    assert season["months"].count("2026-07") == 1
    assert "Visitante" in {row["name"] for row in season["standings"]}


def test_year_with_only_preview_has_no_official_standings(legacy_data, tmp_path):
    from gymrats.storage.schema import participants_to_dict

    original = Repository(legacy_data)
    root = tmp_path / "new-year"
    root.mkdir()
    (root / "participants.json").write_text(
        json.dumps(participants_to_dict(original.participants()))
    )
    repo = Repository(root)
    publisher = Publisher(repo, tmp_path / "site")
    TallyService(repo, publisher).commit(
        "2026-01",
        original.tables("2026-06"),
        provisional=True,
        provenance={"monthly_end": "2026-01-01", "partial_day": True},
    )
    season = json.loads((publisher.out_dir / "season/2026.json").read_text())
    assert season["closed_only"] is True
    assert season["months"] == []
    assert season["standings"] == []
    assert not season.get("provisional")
    assert (publisher.out_dir / "months/2026-01.json").is_file()


def test_snapshot_publication_failure_rolls_back(legacy_data, tmp_path, monkeypatch):
    repo = Repository(legacy_data)
    publisher = Publisher(repo, tmp_path / "site")
    publisher.publish()
    before = {p: p.read_bytes() for p in publisher.out_dir.rglob("*.json")}
    write, failed = Path.write_bytes, []

    def fail_once(path, content):
        if path == publisher.out_dir / "index.json" and not failed:
            failed.append(True)
            raise OSError("disk failed")
        return write(path, content)

    monkeypatch.setattr(Path, "write_bytes", fail_once)
    with pytest.raises(OSError, match="disk failed"):
        TallyService(repo, publisher).commit(
            "2026-07", repo.tables("2026-06"), provenance=provenance(), provisional=True
        )
    assert not repo.provisional_path("2026-07").exists()
    assert before == {p: p.read_bytes() for p in publisher.out_dir.rglob("*.json")}
