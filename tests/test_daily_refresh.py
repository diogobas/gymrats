"""Offline automation checks, including Sao Paulo midnight and month rollover."""

from __future__ import annotations

import json
import secrets
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from gymrats.collection.client import CollectorError, save_private
from gymrats.collection.service import SessionService
from gymrats.core.models import Entry, Modality, Participant, Period, Tables
from gymrats.refresh_daily import TIMEZONE, main, refresh, seal_captures, targets
from gymrats.storage.publisher import Publisher
from gymrats.storage.repository import Repository


@pytest.fixture
def synthetic(legacy_data, tmp_path, monkeypatch):
    repo = Repository(legacy_data)
    repo.write_participants([Participant("Arthur"), Participant("Diogo")])
    (repo.root / "history/2026.json").write_text(json.dumps({"ranked": {}}))
    tables = Tables.build(
        {
            (modality, period): [Entry("Arthur", 10, 1), Entry("Diogo", 5, 2)]
            for modality in Modality
            for period in Period
            if period == Period.MONTH
            or modality in (Modality.DISTANCE, Modality.DURATION)
        }
    )
    for number in range(1, 10):
        repo.write_tables(f"2026-{number:02d}", tables)
    site, private = tmp_path / "site", tmp_path / "private"
    Publisher(repo, site).publish()
    save_private(
        private / "session.json", {"token": "test-token", "signature": "test-sig"}
    )
    monkeypatch.setattr("gymrats.collection.service.sleep", lambda _: None)
    return repo, site, private


def fake_session(private, monkeypatch, now, *, fail_at=None, changed_members=False):
    monkeypatch.setattr(
        "gymrats.collection.service.date_in_timezone",
        lambda _: now.astimezone(ZoneInfo(TIMEZONE)).date(),
    )
    calls = []

    def transport(path, **kwargs):
        assert kwargs["timezone"] == TIMEZONE
        if path == "/account":
            return {"status": "success", "data": {"id": 1}}
        if path == "/challenges":
            return {
                "status": "success",
                "data": [{"id": 2504035, "joined_at": "2026-01-01"}],
            }
        calls.append(dict(kwargs["params"]))
        if len(calls) == fail_at:
            raise CollectorError("HTTP 429. Limite atingido.")
        names = ["Arthur"] if changed_members else ["Arthur", "Diogo"]
        return {
            "status": "success",
            "data": [
                {
                    "account": {"id": i, "full_name": name},
                    "score": str(15 - i * 5),
                    "rank": i,
                }
                for i, name in enumerate(names, 1)
            ],
        }

    return SessionService(private, transport, timezone=TIMEZONE), calls


def before_files(repo, site):
    return {p: p.read_bytes() for root in (repo.root, site) for p in root.rglob("*.json")}


def test_midnight_sao_paulo_is_a_different_day_than_toronto(synthetic, monkeypatch):
    repo, site, private = synthetic
    now = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)
    assert now.astimezone(ZoneInfo("America/Toronto")).day == 27
    session, calls = fake_session(private, monkeypatch, now)
    closed = {p: p.read_bytes() for p in (repo.root / "months").glob("*.json")}
    report = refresh(repo, site, private, session, now=now)
    assert report == [
        {
            "month": "2026-10",
            "through": "2026-10-27",
            "pending_review": False,
            "changed": True,
        }
    ]
    assert len(calls) == 7
    assert {p["end_date"] for p in calls} == {"2026-10-27"}
    assert all(p.read_bytes() == content for p, content in closed.items())
    snapshot = json.loads(repo.provisional_path("2026-10").read_text())
    assert snapshot["provenance"]["timezone"] == TIMEZONE
    assert snapshot["provenance"]["automated"] is True
    again = before_files(repo, site)
    assert refresh(repo, site, private, session, now=now)[0]["changed"] is False
    assert before_files(repo, site) == again


def test_rollover_prepares_previous_month_without_closing_it(synthetic, monkeypatch):
    repo, site, private = synthetic
    now = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    session, calls = fake_session(private, monkeypatch, now)
    report = refresh(repo, site, private, session, now=now)
    assert report[0]["through"] == "2026-10-31"
    assert report[0]["pending_review"] is True
    assert not repo.month_path("2026-10").exists()
    assert repo.provisional_info("2026-10")["pending_review"] is True
    assert {p["end_date"] for p in calls} == {"2026-10-31"}
    # November starts after its first complete day, while October awaits review.
    now = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)
    session, calls = fake_session(private, monkeypatch, now)
    report = refresh(repo, site, private, session, now=now)
    assert [r["month"] for r in report] == ["2026-11"]
    assert len(calls) == 7
    season = json.loads((site / "season/2026.json").read_text())
    assert season["months"][-2:] == ["2026-10", "2026-11"]
    assert len(season["months"]) == len(set(season["months"]))
    assert "2026-10" not in repo.months()


def test_missed_rollover_catches_up_atomically(synthetic, monkeypatch):
    repo, site, private = synthetic
    now = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)
    session, _ = fake_session(private, monkeypatch, now, fail_at=8)
    before = before_files(repo, site)
    with pytest.raises(CollectorError, match="429"):
        refresh(repo, site, private, session, now=now)
    assert before_files(repo, site) == before
    assert list((private / "collections").glob("*/month-points.json"))


def test_manual_refresh_opens_november_on_first_day(synthetic, monkeypatch):
    repo, site, private = synthetic
    repo.write_tables("2026-10", repo.tables("2026-09"))
    Publisher(repo, site).publish()
    now = datetime(2026, 11, 1, 15, 0, tzinfo=UTC)
    assert targets(repo, now) == []
    assert [
        (month, end.isoformat()) for month, end in targets(repo, now, include_today=True)
    ] == [("2026-11", "2026-11-01")]
    session, calls = fake_session(private, monkeypatch, now)
    closed = {p: p.read_bytes() for p in (repo.root / "months").glob("*.json")}
    report = refresh(repo, site, private, session, now=now, include_today=True)
    assert report == [
        {
            "month": "2026-11",
            "through": "2026-11-01",
            "pending_review": False,
            "changed": True,
        }
    ]
    assert len(calls) == 7
    assert {call["end_date"] for call in calls} == {"2026-11-01"}
    index = json.loads((site / "index.json").read_text())
    assert index["latest_month"] == "2026-11"
    assert index["latest_completed_month"] == "2026-10"
    assert index["months"][-1]["partial_day"] is True
    for path in ("months/2026-11.json", "season/2026.json"):
        document = json.loads((site / path).read_text())
        assert document["partial_day"] is True
        assert document["provisional"] is True
        assert document["data_through"] == "2026-11-01"
        assert not document.get("pending_review")
    assert all(path.read_bytes() == content for path, content in closed.items())


def test_partial_last_day_cannot_be_closed_and_daily_refresh_completes_it(
    synthetic, monkeypatch
):
    repo, site, private = synthetic
    now = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
    session, _ = fake_session(private, monkeypatch, now)
    refresh(repo, site, private, session, now=now, include_today=True)
    assert repo.provisional_info("2026-10")["partial_day"] is True
    assert not repo.provisional_info("2026-10").get("pending_review")
    assert "2026-10" not in repo.complete_provisional_months()
    now = datetime(2026, 11, 1, 3, 7, tzinfo=UTC)
    session, calls = fake_session(private, monkeypatch, now)
    report = refresh(repo, site, private, session, now=now)
    # Same tables and same cutoff; the partial/complete metadata still changes.
    assert report[0]["changed"] is True
    assert len(calls) == 7
    info = repo.provisional_info("2026-10")
    assert info["pending_review"] is True
    assert not info.get("partial_day")
    assert "2026-10" in repo.complete_provisional_months()


def test_daily_refresh_never_rolls_back_a_more_recent_manual_snapshot(
    synthetic, monkeypatch
):
    repo, site, private = synthetic
    now = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
    session, _ = fake_session(private, monkeypatch, now)
    refresh(repo, site, private, session, now=now, include_today=True)
    before = before_files(repo, site)
    assert targets(repo, now) == []
    assert refresh(repo, site, private, session, now=now) == []
    assert before_files(repo, site) == before


@pytest.mark.parametrize("valid_positions", [True, False])
def test_intraday_ties_are_visible_but_data_issues_still_block_publication(
    synthetic, monkeypatch, valid_positions
):
    repo, site, private = synthetic
    now = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
    session, _ = fake_session(private, monkeypatch, now)
    transport = session.transport

    def tied(path, **kwargs):
        response = transport(path, **kwargs)
        if path.endswith("/rankings"):
            for row in response["data"]:
                row.update(score="10", rank=1 if valid_positions else 2)
        return response

    session.transport = tied
    before = before_files(repo, site)
    if not valid_positions:
        with pytest.raises(CollectorError, match="conferência"):
            refresh(repo, site, private, session, now=now, include_today=True)
        assert before_files(repo, site) == before
        return
    report = refresh(repo, site, private, session, now=now, include_today=True)
    assert report[0]["pending_ties"] is True
    document = json.loads((site / "months/2026-10.json").read_text())
    assert document["partial_day"] is True
    assert document["unresolved_ties"] == [["Arthur", "Diogo"]]
    assert {row["position"] for row in document["standings"]} == {1}
    assert not repo.month_path("2026-10").exists()
    # Complete-day daily collection retains its existing requirement to review ties.
    before = before_files(repo, site)
    tomorrow = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "gymrats.collection.service.date_in_timezone", lambda _: tomorrow.date()
    )
    with pytest.raises(CollectorError, match="Empates pendentes"):
        refresh(repo, site, private, session, now=tomorrow)
    assert before_files(repo, site) == before


def test_intraday_mode_rejects_future_cutoffs_and_closed_collection(
    synthetic, monkeypatch
):
    from datetime import date

    from gymrats.collection.service import CollectionService
    from gymrats.storage.tally_service import TallyService

    repo, site, private = synthetic
    now = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
    session, _ = fake_session(private, monkeypatch, now)
    service = CollectionService(
        private,
        repo,
        TallyService(repo, Publisher(repo, site)),
        session=session,
        timezone=TIMEZONE,
    )
    with pytest.raises(CollectorError, match="Corte inválido"):
        service.start("2026-10", True, through=date(2026, 10, 29), include_today=True)
    with pytest.raises(CollectorError, match="Corte inválido"):
        service.start("2026-10", True, through=date(2026, 10, 28))
    with pytest.raises(CollectorError, match="só pode ser incluído"):
        service.start("2026-09", False, include_today=True)


def test_intraday_targets_use_sao_paulo_date_and_stay_in_2026(synthetic):
    repo, _, _ = synthetic
    before_midnight = datetime(2026, 11, 1, 2, 59, tzinfo=UTC)
    after_midnight = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    assert targets(repo, before_midnight, include_today=True)[-1][0] == "2026-10"
    assert targets(repo, after_midnight, include_today=True)[-1][0] == "2026-11"
    assert all(
        month.startswith("2026-")
        for month, _ in targets(
            repo, datetime(2027, 1, 2, 3, tzinfo=UTC), include_today=True
        )
    )


def test_changed_participants_do_not_replace_the_site(synthetic, monkeypatch):
    repo, site, private = synthetic
    now = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)
    session, _ = fake_session(private, monkeypatch, now, changed_members=True)
    before = before_files(repo, site)
    with pytest.raises(CollectorError, match="Participantes mudaram"):
        refresh(repo, site, private, session, now=now)
    assert before_files(repo, site) == before


def test_manual_corrections_are_preserved(synthetic, monkeypatch):
    repo, site, private = synthetic
    now = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)
    session, _ = fake_session(private, monkeypatch, now)
    refresh(repo, site, private, session, now=now)
    path = repo.provisional_path("2026-10")
    doc = json.loads(path.read_text())
    doc["provenance"]["revision"] = 2
    path.write_text(json.dumps(doc))
    before = before_files(repo, site)
    with pytest.raises(CollectorError, match="correções manuais"):
        refresh(repo, site, private, session, now=now)
    assert before_files(repo, site) == before


def test_sao_paulo_date_and_year_boundaries(synthetic):
    repo, _, _ = synthetic
    before_midnight = datetime(2026, 10, 28, 2, 59, tzinfo=UTC)
    assert targets(repo, before_midnight)[0][1].isoformat() == "2026-10-26"
    assert targets(repo, datetime(2026, 1, 1, 3, tzinfo=UTC)) == []
    assert targets(repo, datetime(2027, 1, 1, 3, tzinfo=UTC))[-1][0] == "2026-12"
    assert all(
        month.startswith("2026-")
        for month, _ in targets(repo, datetime(2027, 1, 2, 3, tzinfo=UTC))
    )


def test_raw_archive_excludes_session_and_does_not_put_key_in_command(
    tmp_path, monkeypatch
):
    private, output = tmp_path / "private", tmp_path / "captures.gpg"
    save_private(private / "session.json", {"token": "secret-session"})
    save_private(private / "collections/run/manifest.json", {"status": "partial"})
    key = secrets.token_urlsafe(32)

    def encrypt(command, **kwargs):
        assert key not in " ".join(command)
        assert "secret-session" not in " ".join(command)
        passphrase = Path(command[command.index("--passphrase-file") + 1])
        assert passphrase.read_text(encoding="utf-8") == key
        assert passphrase.stat().st_mode & 0o777 == 0o600
        with tarfile.open(command[-1]) as archive:
            assert all(name.startswith("collections") for name in archive.getnames())
            assert not any("session.json" in name for name in archive.getnames())
        output.write_bytes(b"encrypted-fixture")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("gymrats.refresh_daily.subprocess.run", encrypt)
    seal_captures(private, output, key)
    assert output.read_bytes() == b"encrypted-fixture"


def test_missing_secret_fails_without_exposing_values(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GYMRATS_SESSION_JSON", raising=False)
    monkeypatch.delenv("GYMRATS_ARCHIVE_KEY", raising=False)
    assert main(["--private", str(tmp_path)]) == 1
    assert not (tmp_path / "session.json").exists()
    assert "Atualização não publicada" in capsys.readouterr().out


def test_expired_session_cleanup_and_safe_error(tmp_path, monkeypatch, capsys):
    secret = "never-print-this-token"
    monkeypatch.setenv(
        "GYMRATS_SESSION_JSON", json.dumps({"token": secret, "signature": "sig"})
    )

    def expired(*args, **kwargs):
        raise CollectorError("HTTP 401. Sessão expirada.")

    monkeypatch.setattr("gymrats.refresh_daily.refresh", expired)
    assert main(["--private", str(tmp_path)]) == 1
    assert not (tmp_path / "session.json").exists()
    assert secret not in capsys.readouterr().out


def test_final_copy_failure_restores_all_files(synthetic, monkeypatch):
    from gymrats.refresh_daily import _write_all

    repo, site, _ = synthetic
    existing = repo.provisional_path("2026-10")
    existing.parent.mkdir(exist_ok=True)
    existing.write_bytes(b"original")
    new = repo.provisional_path("2026-11")
    index = site / "index.json"
    original = index.read_bytes()
    write, failed = Path.write_bytes, []

    def fail_once(path, content):
        if path == index and not failed:
            failed.append(True)
            raise OSError("disk full")
        return write(path, content)

    monkeypatch.setattr(Path, "write_bytes", fail_once)
    with pytest.raises(OSError, match="disk full"):
        _write_all({existing: b"updated", new: b"new", index: b"updated"})
    assert existing.read_bytes() == b"original"
    assert not new.exists()
    assert index.read_bytes() == original
