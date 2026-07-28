"""The API, end to end, against a throwaway copy of the real data.

The routes are supposed to be thin, so most of what is worth asserting here is
the wiring: that a screenshot uploaded from a phone comes back as an image, a
correction survives a discarded tab, and a commit writes exactly the two
things it is supposed to write.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="a suíte do núcleo roda sem a extra api")

from fastapi.testclient import TestClient
from gymrats.api.app import create_app
from gymrats.api.config import Settings

DATA = Path(__file__).resolve().parents[1] / "data"
PNG = b"\x89PNG\r\n\x1a\n fake"


@pytest.fixture
def settings(tmp_path):
    shutil.copytree(DATA, tmp_path / "data")
    return Settings(
        data=tmp_path / "data",
        site=tmp_path / "site",
        inbox=tmp_path / "inbox",
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def upload(client, *names):
    files = [("files", (name, PNG, "image/png")) for name in names]
    response = client.post("/api/ingest/upload", files=files)
    assert response.status_code == 200, response.text
    return response.json()


def hustle_table(rows):
    return {
        "modality": "hustle",
        "period": "month",
        "rows": [
            {"name": name, "raw_value": value, "position": position}
            for position, (name, value) in enumerate(rows, start=1)
        ],
    }


# -- health ----------------------------------------------------------------


def test_health_says_which_plugins_are_wired(client):
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["source"] == "upload"
    assert body["ocr_engine"] == "manual"


# -- ingest ----------------------------------------------------------------


def test_uploading_from_the_camera_roll_makes_a_batch(client):
    body = upload(client, "IMG_0001.PNG", "IMG_0002.PNG")

    assert len(body["items"]) == 2
    assert body["items"][0]["filename"] == "IMG_0001.PNG"
    assert body["batch_id"]


def test_a_screenshot_comes_back_for_the_review_screen(client):
    body = upload(client, "IMG_0001.PNG")
    item = body["items"][0]

    response = client.get(f"/api/ingest/{body['batch_id']}/items/{item['id']}/image")

    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"


def test_a_forged_identifier_finds_nothing(client):
    body = upload(client, "IMG_0001.PNG")

    response = client.get(
        f"/api/ingest/{body['batch_id']}/items/..%2F..%2Fparticipants.json/image"
    )

    assert response.status_code == 404


def test_scanning_lists_what_is_waiting(client):
    upload(client, "a.png", "b.png")

    body = client.post("/api/ingest/scan").json()

    assert body["source"] == "upload"
    assert len(body["batches"]) == 1
    assert len(body["batches"][0]["items"]) == 2


def test_upload_is_refused_when_another_source_is_active(tmp_path, settings):
    """Better than a 404 on a route that plainly exists."""
    settings.source = "local_folder"
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/ingest/upload", files=[("files", ("a.png", PNG, "image/png"))]
        )

    assert response.status_code == 409
    assert "local_folder" in response.json()["detail"]


# -- reading and correcting ------------------------------------------------


def test_the_manual_engine_opens_one_blank_table_per_screenshot(client):
    """Read nothing, and say so, once per screenshot.

    Every screenshot comes back as its own table with no modality, no period
    and no rows -- which is exactly the review screen's starting state: the
    image on one side, "qual tabela é essa?" on the other.
    """
    body = upload(client, "hustle-mes.png", "hustle-ano.png")

    draft = client.post(f"/api/ocr/{body['batch_id']}?month=2026-07").json()

    assert draft["month"] == "2026-07"
    assert [table["sources"] for table in draft["tables"]] == [
        ["01-hustle-mes.png"],
        ["02-hustle-ano.png"],
    ]
    assert {issue["type"] for issue in draft["issues"]} == {
        "missing_modality",
        "missing_period",
    }


def test_reading_a_batch_with_nothing_pending_is_a_404(client):
    assert client.post("/api/ocr/nao-existe").status_code == 404


def test_a_correction_survives_the_tab_being_discarded(client):
    """The review happens on a phone. Safari drops background tabs."""
    batch = upload(client, "hustle.png")["batch_id"]
    client.post(f"/api/ocr/{batch}")

    saved = client.put(
        f"/api/ocr/{batch}/draft",
        json={
            "month": "2026-07",
            "tables": [hustle_table([("Arthur", "356.50 pontos")])],
        },
    )
    assert saved.status_code == 200

    reloaded = client.get(f"/api/ocr/{batch}/draft").json()
    assert reloaded["month"] == "2026-07"
    assert reloaded["tables"][0]["rows"][0]["raw_value"] == "356.50 pontos"
    assert reloaded["tables"][0]["rows"][0]["resolved_name"] == "Arthur"


def test_the_draft_is_judged_again_after_the_roster_changes(client):
    """A name registered mid-review must stop being unknown."""
    batch = upload(client, "hustle.png")["batch_id"]
    client.put(
        f"/api/ocr/{batch}/draft",
        json={"month": "2026-07", "tables": [hustle_table([("Fulano", "10 pontos")])]},
    )
    assert client.get(f"/api/ocr/{batch}/draft").json()["issues"][0]["type"] == (
        "unknown_name"
    )

    client.post("/api/participants", json={"name": "Fulano"})

    assert client.get(f"/api/ocr/{batch}/draft").json()["issues"] == []


def test_an_issue_arrives_written_out_in_portuguese(client):
    batch = upload(client, "hustle.png")["batch_id"]

    body = client.put(
        f"/api/ocr/{batch}/draft",
        json={
            "month": "2026-07",
            # The app numbered Arthur first; 10 does not come before 500.
            "tables": [hustle_table([("Arthur", "10 pontos"), ("Diogo", "500 pontos")])],
        },
    ).json()

    messages = {issue["type"]: issue["message"] for issue in body["issues"]}
    assert "position_mismatch" in messages
    assert "1º" in messages["position_mismatch"]


# -- the roster ------------------------------------------------------------


def test_linking_an_unknown_name_teaches_the_roster_an_alias(client):
    """The fix that lasts: next month the same screenshot resolves itself."""
    response = client.patch(
        "/api/participants/Túlio", json={"aliases": ["Tulio", "TÚLIO S."]}
    )

    assert response.status_code == 200
    tulio = next(p for p in response.json()["participants"] if p["name"] == "Túlio")
    assert tulio["aliases"] == ["Tulio", "TÚLIO S."]


def test_registering_someone_who_is_already_there_is_refused(client):
    assert client.post("/api/participants", json={"name": "Arthur"}).status_code == 409


def test_patching_a_stranger_is_a_404(client):
    assert client.patch("/api/participants/Ninguém", json={}).status_code == 404


# -- preview and commit ----------------------------------------------------


def july_body(batch: str | None = None) -> dict:
    tables = [
        {
            "modality": modality,
            "period": "month",
            "rows": [
                {"name": "Arthur", "raw_value": first, "position": 1},
                {"name": "Diogo", "raw_value": second, "position": 2},
            ],
        }
        for modality, first, second in (
            ("hustle", "300.00 pontos", "200.00 pontos"),
            ("active_days", "20 dias ativo", "18 dias ativo"),
            ("calories", "9,000 calorias", "8,000 calorias"),
        )
    ]
    return {
        "month": "2026-07",
        "batch": batch,
        "draft": {"month": "2026-07", "tables": tables},
    }


def test_a_preview_changes_nothing_on_disk(client, settings):
    body = client.post("/api/tally/preview", json=july_body()).json()

    assert body["committed"] is False
    assert [row["name"] for row in body["month"]["standings"]] == ["Arthur", "Diogo"]
    assert body["season"]["months"][-1] == "2026-07"
    assert not (settings.data / "months" / "2026-07.json").exists()


def test_committing_writes_the_month_and_republishes(client, settings):
    body = client.post("/api/tally/commit", json=july_body()).json()

    assert body["committed"] is True
    stored = json.loads((settings.data / "months" / "2026-07.json").read_text("utf-8"))
    assert stored["month"] == "2026-07"

    index = json.loads((settings.site / "index.json").read_text("utf-8"))
    assert index["latest_month"] == "2026-07"


def test_committing_retires_the_screenshots_of_that_batch(client, settings):
    batch = upload(client, "a.png", "b.png")["batch_id"]

    client.post("/api/tally/commit", json=july_body(batch))

    assert client.post("/api/ingest/scan").json()["batches"] == []
    assert sorted(
        path.name for path in (settings.inbox / batch / "processed").iterdir()
    ) == ["01-a.png", "02-b.png"]


def test_issues_do_not_block_a_commit(client, settings):
    """The admin is the final authority; the screen is what insists."""
    body = july_body()
    body["draft"]["tables"].append(hustle_table([("Fulano", "ilegível")]))

    response = client.post("/api/tally/commit", json=body).json()

    assert response["committed"] is True
    assert {issue["type"] for issue in response["issues"]} >= {
        "unknown_name",
        "unparsed_value",
    }
    assert (settings.data / "months" / "2026-07.json").is_file()


# -- export ----------------------------------------------------------------


def test_the_csv_carries_the_bonus_and_the_raw_calories(client):
    response = client.get("/api/export/2026-06.csv")

    assert response.status_code == 200
    lines = response.text.splitlines()
    assert lines[0].startswith("posicao,nome,pontos")
    andressa = next(line for line in lines if line.startswith("2,Andressa"))
    assert ",10593.0,12711.6,sim," in andressa


def test_exporting_a_month_that_was_never_tallied_is_a_404(client):
    assert client.get("/api/export/2026-12.csv").status_code == 404


# -- the phone -------------------------------------------------------------


def test_the_boot_banner_prints_an_address_to_open_on_the_phone():
    """The screenshots are on the phone, so this is the point of `serve`."""
    from gymrats.api.banner import lan_address, startup_banner

    banner = startup_banner(8000, source="upload", engine="manual", site_port=5173)
    host = lan_address()

    assert "no celular" in banner or "sem rede local" in banner
    if host is not None:
        assert f"http://{host}:5173" in banner


@pytest.mark.parametrize(
    "origin",
    ["http://192.168.0.14:5173", "http://10.0.0.2:5173", "http://localhost:5173"],
)
def test_the_phone_on_the_wifi_is_allowed_through_cors(client, origin):
    response = client.get("/api/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin


def test_the_open_internet_is_not(client):
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers
