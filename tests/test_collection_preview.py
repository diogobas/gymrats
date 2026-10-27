"""Exercise the standalone preview against complete collection artifacts."""

import json
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
