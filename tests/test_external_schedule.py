"""Provisioning must not duplicate jobs or disclose the stored GitHub token."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "external_schedule", Path(__file__).parents[1] / "scripts/setup_external_schedule.py"
)
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)


def test_incomplete_listing_cannot_create_duplicate(monkeypatch):
    monkeypatch.setattr(
        scheduler, "request", lambda *args: {"someFailed": True, "jobs": []}
    )
    with pytest.raises(RuntimeError, match="incompleta"):
        scheduler.find_job("secret")


def test_duplicate_jobs_require_manual_resolution(monkeypatch):
    job = {
        "jobId": 1,
        "title": scheduler.TITLE,
        "url": f"{scheduler.WORKFLOW}/dispatches",
    }
    monkeypatch.setattr(scheduler, "request", lambda *args: {"jobs": [job, job]})
    with pytest.raises(RuntimeError, match="mais de um"):
        scheduler.find_job("secret")


def test_configure_reuses_existing_job_and_hides_credentials(monkeypatch, capsys):
    calls = []
    saved = {}
    existing = {
        "jobId": 42,
        "title": scheduler.TITLE,
        "url": f"{scheduler.WORKFLOW}/dispatches",
    }

    def api(method, url, token, payload=None):
        calls.append((method, url))
        if url == scheduler.WORKFLOW:
            return {"state": "active"}
        if url.endswith("/jobs"):
            return {"jobs": [existing]}
        if method == "PATCH":
            saved.update(payload["job"])
            return {}
        if url.endswith("/history"):
            return {"history": [{"date": 1, "status": 1, "headers": "github-secret"}]}
        return {"jobDetails": saved}

    monkeypatch.setattr(scheduler, "request", api)
    scheduler.configure({"cron_api_key": "cron-secret", "github_token": "github-secret"})
    assert ("PATCH", f"{scheduler.CRON_API}/jobs/42") in calls
    assert all(method not in ("PUT", "POST") for method, _ in calls)
    assert saved["schedule"]["hours"] == [0]
    assert saved["schedule"]["minutes"] == [2]
    assert saved["schedule"]["timezone"] == "America/Toronto"
    output = capsys.readouterr().out
    assert "github-secret" not in output
    assert "cron-secret" not in output


def test_credentials_are_private_and_not_echoed(tmp_path, monkeypatch, capsys):
    target = tmp_path / "private/credentials.json"
    monkeypatch.setattr(scheduler, "CREDENTIALS", target)
    tokens = iter(["cron-secret", "github-secret"])
    monkeypatch.setattr(scheduler.getpass, "getpass", lambda _: next(tokens))
    scheduler.save_credentials()
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700
    output = capsys.readouterr().out
    assert "github-secret" not in output
    assert "cron-secret" not in output


def test_new_job_is_created_with_post_dispatch(monkeypatch):
    saved = {}

    def api(method, url, token, payload=None):
        if url == scheduler.WORKFLOW:
            return {"state": "active"}
        if url.endswith("/jobs") and method == "GET":
            return {"jobs": []}
        if method == "PUT":
            saved.update(payload["job"])
            return {"jobId": 42}
        return {"jobDetails": saved}

    monkeypatch.setattr(scheduler, "request", api)
    monkeypatch.setattr(scheduler, "status", lambda _: None)
    scheduler.configure({"cron_api_key": "cron-secret", "github_token": "github-secret"})
    assert saved["requestMethod"] == 1
    assert saved["extendedData"]["body"] == '{"ref": "master"}'
    assert saved["url"] == f"{scheduler.WORKFLOW}/dispatches"


def test_saved_configuration_must_match(monkeypatch):
    def api(method, url, token, payload=None):
        if url == scheduler.WORKFLOW:
            return {"state": "active"}
        if url.endswith("/jobs") and method == "GET":
            return {"jobs": []}
        if method == "PUT":
            return {"jobId": 42}
        return {"jobDetails": {"enabled": False}}

    monkeypatch.setattr(scheduler, "request", api)
    with pytest.raises(RuntimeError, match="nao confirmou"):
        scheduler.configure(
            {"cron_api_key": "cron-secret", "github_token": "github-secret"}
        )


def test_reschedule_changes_only_time_and_enablement(monkeypatch, capsys):
    job = {
        "jobId": 42,
        "title": scheduler.TITLE,
        "url": f"{scheduler.WORKFLOW}/dispatches",
        "requestMethod": 1,
        "enabled": True,
        "schedule": {"minutes": [7]},
        "extendedData": {
            "headers": {"Authorization": "Bearer existing-private-token"},
            "body": '{"ref":"master"}',
        },
    }
    calls = []

    def api(method, url, token, payload=None):
        if url.endswith("/jobs"):
            return {"jobs": [job.copy()]}
        if method == "PATCH":
            calls.append(payload["job"])
            job.update(payload["job"])
            return {}
        return {"jobDetails": job.copy()}

    monkeypatch.setattr(scheduler, "request", api)
    monkeypatch.setattr(scheduler, "status", lambda _: None)
    scheduler.reschedule({"cron_api_key": "cron-secret"})
    assert calls == [{"enabled": True, "schedule": scheduler.SCHEDULE}]
    assert (
        job["extendedData"]["headers"]["Authorization"] == "Bearer existing-private-token"
    )
    output = capsys.readouterr().out
    assert "00:02 de Toronto" in output
    assert "private-token" not in output
    assert "cron-secret" not in output


@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        (datetime(2026, 11, 3, 5, 2, tzinfo=UTC), "2026-11-03T00:02:00-05:00"),
        (datetime(2026, 7, 3, 4, 2, tzinfo=UTC), "2026-07-03T00:02:00-04:00"),
    ],
)
def test_status_reports_toronto_midnight_across_dst(
    monkeypatch, capsys, instant, expected
):
    job = {
        "jobId": 42,
        "title": scheduler.TITLE,
        "url": f"{scheduler.WORKFLOW}/dispatches",
        "nextExecution": int(instant.timestamp()),
    }
    monkeypatch.setattr(
        scheduler,
        "request",
        lambda method, url, token: (
            {"history": []} if url.endswith("/history") else {"jobs": [job]}
        ),
    )
    scheduler.status({"cron_api_key": "cron-secret"})
    assert f"Proxima execucao em Toronto: {expected}" in capsys.readouterr().out
