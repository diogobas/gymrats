"""Closing a reviewed snapshot changes status, never the reviewed numbers."""

import json
from datetime import UTC, datetime

import pytest
from gymrats.close_month import close_month
from gymrats.collection.client import CollectorError
from gymrats.core.models import Entry, Modality, Participant, Period, Tables
from gymrats.storage.publisher import Publisher
from gymrats.storage.repository import Repository
from gymrats.storage.tally_service import TallyService

REVISION = "a" * 40
NOW = datetime(2026, 8, 1, 3, tzinfo=UTC)


@pytest.fixture
def snapshot(tmp_path):
    repo = Repository(tmp_path / "data")
    repo.write_participants([Participant("Arthur"), Participant("Diogo")])
    tables = Tables.build(
        {
            (metric, period): [Entry("Arthur", 10, 1), Entry("Diogo", 5, 2)]
            for metric in Modality
            for period in Period
            if period == Period.MONTH or metric in (Modality.DISTANCE, Modality.DURATION)
        }
    )
    for number in range(1, 7):
        repo.write_tables(f"2026-{number:02d}", tables)
    site = tmp_path / "site"
    TallyService(repo, Publisher(repo, site)).commit(
        "2026-07",
        tables,
        provisional=True,
        provenance={
            "source": "gymrats_api",
            "challenge_id": 2504035,
            "monthly_start": "2026-07-01",
            "monthly_end": "2026-07-31",
            "annual_start": "2026-01-01",
            "annual_end": "2026-07-31",
            "pending_review": True,
            "timezone": "America/Sao_Paulo",
        },
    )
    return repo, site


def close(snapshot, **kwargs):
    repo, site = snapshot
    return close_month(
        repo,
        site,
        "2026-07",
        REVISION,
        checkout_revision=kwargs.pop("checkout_revision", REVISION),
        now=kwargs.pop("now", NOW),
        **kwargs,
    )


def files(snapshot):
    repo, site = snapshot
    return {p: p.read_bytes() for root in (repo.root, site) for p in root.rglob("*.json")}


def change(snapshot, edit):
    repo, _ = snapshot
    path = repo.provisional_path("2026-07")
    document = json.loads(path.read_text())
    edit(document)
    path.write_text(json.dumps(document))


def test_promotes_exact_snapshot_and_records_review(snapshot):
    repo, site = snapshot
    previous = json.loads((site / "months/2026-07.json").read_text())
    source = repo.provisional_path("2026-07").read_bytes()
    close(snapshot)
    result = json.loads((site / "months/2026-07.json").read_text())
    assert result["standings"] == previous["standings"]
    assert not result.get("provisional")
    assert not result.get("pending_review")
    assert repo.provisional_path("2026-07").read_bytes() == source
    official = json.loads(repo.month_path("2026-07").read_text())
    assert official["provenance"]["reviewed_revision"] == REVISION
    assert official["provenance"]["closed_via"] == "web_admin"
    assert "pending_review" not in official["provenance"]
    assert repo.provisional_months() == ()
    index = json.loads((site / "index.json").read_text())
    assert index["latest_completed_month"] == "2026-07"
    season = json.loads((site / "season/2026.json").read_text())
    assert season["months"].count("2026-07") == 1
    assert not season.get("provisional")
    before = files(snapshot)
    with pytest.raises(CollectorError, match="já foi fechado"):
        close(snapshot)
    assert files(snapshot) == before


@pytest.mark.parametrize(
    "failure",
    [
        "stale",
        "ongoing",
        "partial",
        "not_pending",
        "missing_metric",
        "names",
        "duplicate",
        "invalid_value",
        "ties",
        "missing_previous",
        "public_changed",
    ],
)
def test_invalid_or_stale_confirmation_writes_nothing(snapshot, failure):
    repo, site = snapshot
    options = {}
    if failure == "stale":
        options["checkout_revision"] = "b" * 40
    elif failure == "ongoing":
        options["now"] = datetime(2026, 8, 1, 2, 59, tzinfo=UTC)
    elif failure == "partial":
        change(snapshot, lambda d: d["provenance"].update(monthly_end="2026-07-30"))
    elif failure == "not_pending":
        change(snapshot, lambda d: d["provenance"].update(pending_review=False))
    elif failure == "missing_metric":
        change(snapshot, lambda d: d["tables"].pop("duration"))
    elif failure == "names":
        change(
            snapshot, lambda d: d["tables"]["hustle"]["month"][0].update(name="Unknown")
        )
    elif failure == "duplicate":
        change(
            snapshot,
            lambda d: d["tables"]["hustle"]["month"].append(
                d["tables"]["hustle"]["month"][0]
            ),
        )
    elif failure == "invalid_value":
        change(snapshot, lambda d: d["tables"]["hustle"]["month"][0].update(value=-1))
    elif failure == "ties":

        def tied(d):
            for periods in d["tables"].values():
                for rows in periods.values():
                    rows[1]["value"] = rows[0]["value"]

        change(snapshot, tied)
    elif failure == "missing_previous":
        repo.month_path("2026-06").unlink()
    elif failure == "public_changed":
        path = site / "months/2026-07.json"
        document = json.loads(path.read_text())
        document["standings"][0]["total"] += 1
        path.write_text(json.dumps(document))
    before = files(snapshot)
    with pytest.raises(CollectorError):
        close(snapshot, **options)
    assert files(snapshot) == before


def test_publication_failure_preserves_preview_and_official_files(snapshot, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("simulated publication failure")

    before = files(snapshot)
    monkeypatch.setattr(Publisher, "publish", fail)
    with pytest.raises(OSError, match="simulated"):
        close(snapshot)
    assert files(snapshot) == before
