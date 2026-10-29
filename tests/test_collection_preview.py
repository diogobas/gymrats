"""Exercise the standalone preview against complete collection artifacts."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments/gymrats_collector/preview.py"


@pytest.fixture
def captured(legacy_data, tmp_path):
    data = legacy_data
    original = json.loads((data / "months/2026-06.json").read_text())
    roster = json.loads((data / "participants.json").read_text())["participants"]
    local = tmp_path / ".local"
    (local / "responses").mkdir(parents=True)
    records = []
    metrics = {
        "points": "hustle",
        "days": "active_days",
        "calories": "calories",
        "distance": "distance",
        "duration": "duration",
    }
    for period, metric in [
        *(("month", m) for m in metrics),
        ("year", "distance"),
        ("year", "duration"),
    ]:
        values = {
            r["name"]: r["value"] for r in original["tables"][metrics[metric]][period]
        }
        rows = [
            {
                "account": {"id": i, "full_name": person["name"]},
                "score": str(values.get(person["name"], 0)),
            }
            for i, person in enumerate(roster, 1)
        ]
        file = f"responses/{period}-{metric}.json"
        payload = {
            "path": "/challenges/2504035/rankings",
            "params": [
                ["score_by", metric],
                ["disable_format", "true"],
                ["start_date", "2026-06-01" if period == "month" else "2026-01-01"],
                ["end_date", "2026-06-30"],
            ],
            "response": {"status": "success", "data": rows},
        }
        (local / file).write_text(json.dumps(payload))
        records.append(
            {"period": period, "metric": metric, "file": file, "count": len(rows)}
        )
    folder = local / "collections" / "run"
    folder.mkdir(parents=True)
    manifest = folder / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "challenge_id": 2504035,
                "month": "2026-06",
                "status": "complete",
                "annual_end_date": "2026-06-30",
                "responses": records,
            }
        )
    )
    return local, data, manifest


def run_preview(captured):
    local, data, manifest = captured
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "2026-06",
            "--local",
            str(local),
            "--data",
            str(data),
            "--manifest",
            str(manifest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_preview_uses_existing_tally_and_preserves_source_files(captured):
    _, data, manifest = captured
    before = {p: p.read_bytes() for p in data.rglob("*.json")}
    result = run_preview(captured)
    assert result.returncode == 0, result.stderr
    report = json.loads((manifest.parent / "preview.json").read_text())
    assert report["committed"] is False
    assert report["annual_end_date"] == "2026-06-30"
    assert report["missing_months"] == []
    assert [(r["name"], r["total"]) for r in report["month"]["standings"][:2]] == [
        ("Arthur", 4),
        ("Andressa", 4),
    ]
    assert report["season"]["months"][-1] == "2026-06"
    assert before == {p: p.read_bytes() for p in data.rglob("*.json")}


@pytest.mark.parametrize("status", ["complete", "partial"])
def test_auto_preview_uses_latest_collector_run_among_admin_runs(captured, status):
    local, data, manifest = captured
    doc = json.loads(manifest.read_text())
    doc["status"] = status
    manifest.write_text(json.dumps(doc))
    old = local / "collections/z-old/manifest.json"
    old.parent.mkdir()
    old_doc = dict(doc, status="partial")
    old.write_text(json.dumps(old_doc))
    os.utime(old, ns=(1, 1))
    admin = local / "collections/zz-admin/manifest.json"
    admin.parent.mkdir()
    admin.write_text(json.dumps({"month": "2026-06", "status": "complete"}))
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "2026-06",
            "--local",
            str(local),
            "--data",
            str(data),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if status == "complete":
        assert result.returncode == 0, result.stderr
        assert (manifest.parent / "preview.json").exists()
    else:
        assert result.returncode == 1
        assert "parcial" in result.stderr
        assert not (manifest.parent / "preview.json").exists()


@pytest.mark.parametrize(
    "change", ["partial", "cutoff", "missing", "unknown", "wrong_period", "escape"]
)
def test_preview_rejects_incomplete_or_inconsistent_collections(captured, change):
    local, _, manifest = captured
    doc = json.loads(manifest.read_text())
    if change == "partial":
        doc["status"] = "partial"
    elif change == "cutoff":
        doc["annual_end_date"] = "2026-07-28"
    elif change == "missing":
        doc["responses"].pop()
    elif change == "escape":
        doc["responses"][0]["file"] = "../outside.json"
    else:
        file = local / doc["responses"][0]["file"]
        response = json.loads(file.read_text())
        if change == "unknown":
            response["response"]["data"][0]["account"]["full_name"] = "Unknown"
        else:
            response["params"][-1][1] = "2026-07-01"
        file.write_text(json.dumps(response))
    manifest.write_text(json.dumps(doc))
    result = run_preview(captured)
    assert result.returncode == 1
    assert not (manifest.parent / "preview.json").exists()


def run_import(captured, *options):
    local, data, manifest = captured
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT.with_name("import_month.py")),
            "--manifest",
            str(manifest),
            "--challenge-id",
            "2404482",
            "--local",
            str(local),
            "--data",
            str(data),
            "--out",
            str(local / "site"),
            *options,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def historical_capture(captured):
    local, _, manifest = captured
    doc = json.loads(manifest.read_text())
    doc.update(challenge_id=2404482, month="2025-12", annual_end_date="2025-12-31")
    manifest.write_text(json.dumps(doc))
    for item in doc["responses"]:
        path = local / item["file"]
        capture = json.loads(path.read_text())
        capture["path"] = "/challenges/2404482/rankings"
        capture["params"] = [
            [
                key,
                "2025-12-31"
                if key == "end_date"
                else ("2025-12-01" if item["period"] == "month" else "2025-01-01")
                if key == "start_date"
                else value,
            ]
            for key, value in capture["params"]
        ]
        path.write_text(json.dumps(capture))
    return captured


def test_historical_import_previews_without_saving(historical_capture):
    local, data, _ = historical_capture
    before = {p: p.read_bytes() for p in data.rglob("*.json")}
    result = run_import(historical_capture)
    assert result.returncode == 0, result.stderr
    assert "Acumulado incompleto" in result.stdout
    assert before == {p: p.read_bytes() for p in data.rglob("*.json")}
    assert not (local / "site").exists()


def test_historical_import_requires_explicit_partial_season(historical_capture):
    _, data, _ = historical_capture
    result = run_import(historical_capture, "--commit")
    assert result.returncode == 1
    assert "--allow-incomplete-season" in result.stderr
    assert not (data / "months/2025-12.json").exists()


def test_historical_import_publishes_year_and_protects_existing_month(historical_capture):
    local, data, _ = historical_capture
    before = (data / "months/2026-06.json").read_bytes()
    result = run_import(historical_capture, "--commit", "--allow-incomplete-season")
    assert result.returncode == 0, result.stderr
    index = json.loads((local / "site/index.json").read_text())
    assert index["years"] == [2025, 2026]
    assert index["latest_year"] == 2026
    season = json.loads((local / "site/season/2025.json").read_text())
    assert season["missing_months"] == [f"2025-{m:02d}" for m in range(1, 12)]
    assert season["months"] == ["2025-12"]
    saved = json.loads((data / "months/2025-12.json").read_text())
    assert saved["provenance"]["challenge_id"] == 2404482
    assert ".local" not in json.dumps(saved)
    assert before == (data / "months/2026-06.json").read_bytes()
    result = run_import(historical_capture, "--commit", "--allow-incomplete-season")
    assert result.returncode == 1
    assert "--replace" in result.stderr
    result = run_import(
        historical_capture, "--commit", "--allow-incomplete-season", "--replace"
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("change", ["challenge", "route", "negative", "unknown"])
def test_historical_import_rejects_unreviewed_data(historical_capture, change):
    local, data, manifest = historical_capture
    doc = json.loads(manifest.read_text())
    if change == "challenge":
        doc["challenge_id"] = 2504035
        manifest.write_text(json.dumps(doc))
    else:
        path = local / doc["responses"][0]["file"]
        capture = json.loads(path.read_text())
        if change == "route":
            capture["path"] = "/challenges/2504035/rankings"
        elif change == "negative":
            capture["response"]["data"][0]["score"] = "-1"
        else:
            capture["response"]["data"][0]["account"]["full_name"] = "Unknown"
        path.write_text(json.dumps(capture))
    result = run_import(historical_capture, "--commit", "--allow-incomplete-season")
    assert result.returncode == 1
    assert not (data / "months/2025-12.json").exists()
