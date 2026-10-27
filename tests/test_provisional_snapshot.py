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
    season = json.loads((publisher.out_dir / "season/2026.json").read_text())
    assert season["provisional"] is True
    assert season["data_through"] == "2026-07-26"
    assert season["months"].count("2026-07") == 1
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
