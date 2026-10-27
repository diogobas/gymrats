"""Offline HTTP workflow; no credentials or real GymRats session needed."""

from __future__ import annotations

import json
import shutil
import time
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from gymrats.api.app import create_app
from gymrats.api.config import Settings
from gymrats.collection.client import CollectorError, save_private
from gymrats.collection.service import CollectionService, SessionService, bounds
from gymrats.storage.publisher import Publisher

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def app(tmp_path, monkeypatch):
    shutil.copytree(DATA, tmp_path / "data")
    settings = Settings(
        data=tmp_path / "data",
        site=tmp_path / "site",
        inbox=tmp_path / "inbox",
        private=tmp_path / ".local",
    )
    app = create_app(settings)
    services = app.state.services
    monkeypatch.setattr("gymrats.collection.service.sleep", lambda _: None)
    original = services.repo.tables("2026-06")
    people = services.repo.participants()
    from gymrats.collection.service import METRICS
    from gymrats.core.models import Period

    def transport(path, **kwargs):
        if path == "/accounts/email_confirmation":
            return {"status": "success", "data": {"nonce": "private-nonce"}}
        if path == "/accounts/sign_in":
            assert kwargs["credentials"]["token"] == "123456"
            return {"status": "success", "data": {"token": "private-token"}}
        if path == "/account":
            return {
                "status": "success",
                "data": {
                    "id": 1,
                    "full_name": "Admin",
                    "token": "private-token",
                    "email": "private@email.test",
                },
            }
        if path == "/challenges":
            return {
                "status": "success",
                "data": [{"id": 2504035, "joined_at": "2026-01-01"}],
            }
        params = dict(kwargs["params"])
        metric = METRICS[params["score_by"]]
        period = Period.MONTH if params["start_date"][5:7] != "01" else Period.YEAR
        rows = [
            {
                "account": {"id": i, "full_name": p.name},
                "score": str(original.value_for(p.name, metric, period) or 0),
            }
            for i, p in enumerate(people, 1)
        ]
        return {"status": "success", "data": rows}

    services.gymrats.session.transport = transport
    return app


def connect(client):
    assert (
        client.post(
            "/api/gymrats/session/code", json={"email": "admin@example.test"}
        ).status_code
        == 200
    )
    response = client.post("/api/gymrats/session/verify", json={"code": "123456"})
    assert response.status_code == 200, response.text
    return response


def collect(app, client, month="2026-06"):
    response = client.post("/api/gymrats/runs", json={"month": month})
    assert response.status_code == 202, response.text
    run = response.json()["id"]
    deadline = time.monotonic() + 3
    while app.state.services.gymrats.active and time.monotonic() < deadline:
        time.sleep(0.001)
    return run


def draft_and_preview(app, client):
    connect(client)
    run = collect(app, client)
    draft = client.get(f"/api/gymrats/runs/{run}/draft")
    assert draft.status_code == 200, draft.text
    preview = client.post(f"/api/gymrats/runs/{run}/preview", json={"revision": 1})
    assert preview.status_code == 200, preview.text
    return run, draft.json(), preview.json()


def test_login_allowlist_and_logout(app):
    with TestClient(app) as client:
        assert client.get("/api/gymrats/session").json()["connected"] is False
        response = connect(client)
        status = client.get("/api/gymrats/session")
        for text in (response.text, status.text):
            assert "private-token" not in text
            assert "private-nonce" not in text
            assert "private@email" not in text
        saved = app.state.services.settings.private / "session.json"
        assert saved.stat().st_mode & 0o777 == 0o600
        assert client.delete("/api/gymrats/session").json() == {"connected": False}
        assert not saved.exists()


@pytest.mark.parametrize("failure", ["expired", "no_access", "invalid_account"])
def test_failed_candidate_login_preserves_previous_session(app, failure):
    session = app.state.services.gymrats.session
    save_private(
        session.root / "session.json", {"token": "old", "signature": "old-signature"}
    )
    original = session.transport

    def transport(path, **kw):
        if path == "/account" and failure == "expired":
            raise CollectorError("HTTP 401. Sessão expirada.")
        if path == "/account" and failure == "invalid_account":
            return {"status": "success", "data": {}}
        if path == "/challenges" and failure == "no_access":
            return {"status": "success", "data": []}
        return original(path, **kw)

    session.transport = transport
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/gymrats/session/code", json={"email": "test@example.test"}
            ).status_code
            == 200
        )
        response = client.post("/api/gymrats/session/verify", json={"code": "123456"})
        assert response.status_code == 409
        assert session.load()["token"] == "old"
        assert "private-token" not in response.text
        if failure == "expired":
            assert client.get("/api/gymrats/session").json()["connected"] is False


def test_full_flow_preserves_precision_and_requires_replacement_confirmation(app):
    services = app.state.services
    with TestClient(app) as client:
        run, draft, preview = draft_and_preview(app, client)
        assert len(draft["tables"]) == 7
        duration = next(t for t in draft["tables"] if t["modality"] == "duration")
        assert duration["rows"][0]["raw_value"].endswith(" min")
        assert len(preview["month"]["standings"]) == 10
        assert preview["season"]["months"][-1] == "2026-06"
        body = {"revision": 1, "preview_token": preview["preview_token"]}
        assert (
            client.post(f"/api/gymrats/runs/{run}/commit", json=body).status_code == 409
        )
        response = client.post(
            f"/api/gymrats/runs/{run}/commit", json={**body, "replace": True}
        )
        assert response.status_code == 200, response.text
        assert response.json()["publication"] == "pending_git"
        stored = json.loads(services.repo.month_path("2026-06").read_text())
        assert stored["provenance"]["annual_end"] == "2026-06-30"
        assert "private-token" not in json.dumps(stored)
        assert (services.settings.site / "index.json").exists()


def test_revisions_corrections_resume_and_new_collection(app):
    with TestClient(app) as client:
        run, draft, preview = draft_and_preview(app, client)
        draft["tables"][0]["rows"][0]["raw_value"] = "123.12345678901234"
        response = client.put(f"/api/gymrats/runs/{run}/draft", json=draft)
        assert response.status_code == 200
        updated = response.json()
        assert updated["revision"] == 2
        assert updated["tables"][0]["rows"][0]["value"] == 123.12345678901234
        assert client.put(f"/api/gymrats/runs/{run}/draft", json=draft).status_code == 409
        assert (
            client.post(
                f"/api/gymrats/runs/{run}/preview", json={"revision": 1}
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/gymrats/runs/{run}/commit",
                json={
                    "revision": 1,
                    "preview_token": preview["preview_token"],
                    "replace": True,
                },
            ).status_code
            == 409
        )
        new = collect(app, client)
        assert new != run
        assert client.get(f"/api/gymrats/runs/{run}/draft").json() == updated
        restarted = CollectionService(
            app.state.services.settings.private,
            app.state.services.repo,
            app.state.services.tally,
        )
        assert restarted.load_draft(run) == updated
        assert len(client.get("/api/gymrats/runs").json()["runs"]) == 2


@pytest.mark.parametrize("failure", ["rate_limit", "participants"])
def test_partial_captures_are_preserved_and_cannot_close(app, failure):
    session = app.state.services.gymrats.session
    original, calls = session.transport, []

    def transport(path, **kw):
        if path.endswith("/rankings"):
            calls.append(path)
            if len(calls) == 2 and failure == "rate_limit":
                raise CollectorError("HTTP 429. Limite de requisições atingido.")
        result = original(path, **kw)
        if path.endswith("/rankings") and len(calls) == 2 and failure == "participants":
            result["data"].pop()
        return result

    session.transport = transport
    with TestClient(app) as client:
        connect(client)
        run = collect(app, client)
        state = client.get(f"/api/gymrats/runs/{run}").json()
        assert state["status"] == "partial"
        assert state["completed"] == 1
        assert len(list(app.state.services.gymrats.folder(run).glob("month-*.json"))) >= 1
        assert client.get(f"/api/gymrats/runs/{run}/draft").status_code == 409


def test_restart_marks_running_job_interrupted_and_prevents_overlap(app):
    service = app.state.services.gymrats
    service.active = "in-progress"
    with TestClient(app) as client:
        connect(client)
        assert (
            client.post("/api/gymrats/runs", json={"month": "2026-06"}).status_code == 409
        )
    run = "a" * 32
    save_private(
        service.root / "collections" / run / "manifest.json", {"status": "running"}
    )
    CollectionService(service.root, service.repo, service.tally)
    assert (
        json.loads((service.root / "collections" / run / "manifest.json").read_text())[
            "status"
        ]
        == "interrupted"
    )


@pytest.mark.parametrize(
    "change",
    [
        "unknown",
        "negative",
        "missing_table",
        "names",
        "cutoff",
        "missing_month",
        "invalid",
    ],
)
def test_invalid_drafts_cannot_preview(app, change):
    with TestClient(app) as client:
        run, draft, _ = draft_and_preview(app, client)
        if change == "cutoff":
            path = app.state.services.gymrats.folder(run) / "year-distance.json"
            capture = json.loads(path.read_text())
            capture["params"][-1][1] = "2026-07-01"
            save_private(path, capture)
            assert (
                client.post(
                    f"/api/gymrats/runs/{run}/preview", json={"revision": 1}
                ).status_code
                == 409
            )
            return
        if change == "missing_month":
            (app.state.services.repo.root / "history/2026.json").unlink()
        elif change == "unknown":
            draft["tables"][0]["rows"][0]["name"] = "Pessoa desconhecida"
        elif change == "negative":
            draft["tables"][0]["rows"][0]["raw_value"] = "-3"
        elif change == "invalid":
            draft["tables"][0]["rows"][0]["raw_value"] = "NaN"
        elif change == "missing_table":
            draft["tables"].pop()
        elif change == "names":
            draft["tables"][0]["rows"].pop()
        saved = client.put(f"/api/gymrats/runs/{run}/draft", json=draft)
        assert saved.status_code == 200
        response = client.post(f"/api/gymrats/runs/{run}/preview", json={"revision": 2})
        assert response.status_code == 409, response.text


def test_roster_change_invalidates_preview_and_bonus_is_explicit(app):
    with TestClient(app) as client:
        run, _, preview = draft_and_preview(app, client)
        assert (
            client.patch(
                "/api/participants/Arthur", json={"calorie_bonus": True}
            ).status_code
            == 200
        )
        response = client.post(
            f"/api/gymrats/runs/{run}/commit",
            json={
                "revision": 1,
                "preview_token": preview["preview_token"],
                "replace": True,
            },
        )
        assert response.status_code == 409
        assert "desatualizada" in response.json()["detail"]


def test_month_bounds():
    first, last = bounds("2026-02", today=date(2026, 10, 27))
    assert first.isoformat() == "2026-02-01"
    assert last.isoformat() == "2026-02-28"
    for value in ("2027-01", "2026-99", "2026-2", "2026-12", "2026-10"):
        with pytest.raises(CollectorError):
            bounds(value, today=date(2026, 10, 27))


def test_preview_ignores_later_months_and_deduplicates_history(app):
    service = app.state.services.tally
    repo = app.state.services.repo
    tables = repo.tables("2026-06")
    repo.write_tables("2026-07", tables)
    history = repo.root / "history/2026.json"
    doc = json.loads(history.read_text())
    doc["ranked"]["2026-06"] = ["Arthur"]
    history.write_text(json.dumps(doc))
    result = service.preview("2026-06", tables)
    assert result.season.months == tuple(f"2026-{m:02d}" for m in range(1, 7))
    assert Publisher(repo).season(2026).months.count("2026-06") == 1


def test_failed_publication_restores_previous_files(app, monkeypatch):
    services = app.state.services
    services.tally.publisher.publish()
    before = {
        p: p.read_bytes()
        for root in (services.settings.data, services.settings.site)
        for p in root.rglob("*.json")
    }
    original, failed = Path.write_bytes, []

    def fail_once(path, value):
        if path == services.settings.site / "index.json" and not failed:
            failed.append(path)
            raise OSError("disk error")
        return original(path, value)

    monkeypatch.setattr(Path, "write_bytes", fail_once)
    with pytest.raises(OSError, match="disk error"):
        services.tally.commit("2026-07", services.repo.tables("2026-06"))
    after = {
        p: p.read_bytes()
        for root in (services.settings.data, services.settings.site)
        for p in root.rglob("*.json")
    }
    assert before == after


def test_transport_error_never_echoes_credentials(app):
    # The HTTP transport itself is covered by the compatible CLI tests.
    session = SessionService(
        app.state.services.settings.private,
        transport=lambda *a, **kw: {"status": "error", "token": "secret"},
    )
    with pytest.raises(CollectorError, match="não confirmou sucesso") as error:
        session.request_code("me@example.test")
    assert "secret" not in str(error.value)


def test_numeric_duration_keeps_fractional_minutes(app):
    service = app.state.services.gymrats
    with TestClient(app) as client:
        run, draft, _ = draft_and_preview(app, client)
        table = next(t for t in draft["tables"] if t["modality"] == "duration")
        table["rows"][0]["raw_value"] = "1861.123456789 min"
        updated = client.put(f"/api/gymrats/runs/{run}/draft", json=draft).json()
        table = next(t for t in updated["tables"] if t["modality"] == "duration")
        assert table["rows"][0]["value"] == 1861.123456789
        assert service.preview(run, 2)["revision"] == 2


@pytest.mark.parametrize("value", ["3S6.SO", "1e3", "-0.5", "12.34junk", "1,23"])
def test_partial_numbers_are_invalid_api_corrections(app, value):
    with TestClient(app) as client:
        run, draft, _ = draft_and_preview(app, client)
        draft["tables"][0]["rows"][0]["raw_value"] = value
        assert client.put(f"/api/gymrats/runs/{run}/draft", json=draft).status_code == 200
        assert (
            client.post(
                f"/api/gymrats/runs/{run}/preview", json={"revision": 2}
            ).status_code
            == 409
        )


def test_existing_experimental_captures_do_not_break_the_admin(app):
    root = app.state.services.settings.private
    save_private(
        root / "collections/20261027T120000Z-12345678/manifest.json",
        {"month": "2026-06", "status": "complete", "responses": []},
    )
    service = CollectionService(root, app.state.services.repo, app.state.services.tally)
    assert service.list() == []
    with TestClient(app) as client:
        assert client.get("/api/gymrats/runs").json() == {"runs": []}


@pytest.mark.parametrize("document", [[], {}, {"token": "bad token", "signature": "s"}])
def test_invalid_private_session_is_reported_as_disconnected(app, document):
    save_private(app.state.services.settings.private / "session.json", document)
    with TestClient(app) as client:
        response = client.get("/api/gymrats/session")
        assert response.status_code == 200
        assert response.json()["connected"] is False
