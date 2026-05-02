from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from meshflight_api import storage
from meshflight_api.main import app


ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "scenarios"
TMP_ROOT = ROOT / "artifacts" / "reports" / "test-api-temp"


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def _local_temp_dir(name: str) -> Path:
    path = TMP_ROOT / f"{name}-{uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_save_list_load_and_compile_scenario_api(monkeypatch) -> None:
    temp_artifacts_dir = _local_temp_dir("save-load-compile") / "scenarios"
    monkeypatch.setattr(storage, "ARTIFACTS_DIR", temp_artifacts_dir)

    with TestClient(app) as client:
        scenario_payload = load_fixture("bridge_reconnect.json")

        save_response = client.post("/api/scenarios", json=scenario_payload)
        assert save_response.status_code == 200
        saved = save_response.json()

        scenario_id = saved["scenario_id"]
        assert scenario_id == "bridge-reconnect"
        assert saved["title"] == "Bridge Reconnect"
        saved_path = Path(saved["path"])
        assert saved_path.parts[-3:] == ("bridge-reconnect", "source", "scenario.json")

        list_response = client.get("/api/scenarios")
        assert list_response.status_code == 200
        assert list_response.json() == [
            {
                "scenario_id": "bridge-reconnect",
                "title": "Bridge Reconnect",
                "updated_at": "2026-04-17T18:30:00Z",
                "has_compiled": False,
            }
        ]

        load_response = client.get(f"/api/scenarios/{scenario_id}")
        assert load_response.status_code == 200
        assert load_response.json()["metadata"]["scenario_id"] == "bridge-reconnect"

        compile_response = client.post(f"/api/scenarios/{scenario_id}/compile")
        assert compile_response.status_code == 200
        compiled = compile_response.json()

        assert compiled["scenario_id"] == scenario_id
        source_path = Path(compiled["source_path"])
        assert source_path.parts[-3:] == ("bridge-reconnect", "source", "scenario.json")
        compiled_path = Path(compiled["compiled_path"])
        assert compiled_path.parts[-3:] == ("bridge-reconnect", "compiled", "compiled.json")
        report_path = Path(compiled["report_path"])
        assert report_path.parts[-3:] == ("bridge-reconnect", "compiled", "compile_report.json")

        assert (temp_artifacts_dir / "bridge-reconnect" / "source" / "scenario.json").exists()
        assert (temp_artifacts_dir / "bridge-reconnect" / "compiled" / "compiled.json").exists()
        assert (temp_artifacts_dir / "bridge-reconnect" / "compiled" / "compile_report.json").exists()

        list_after_compile_response = client.get("/api/scenarios")
        assert list_after_compile_response.status_code == 200
        assert list_after_compile_response.json()[0]["has_compiled"] is True


def test_save_api_generates_unique_name_for_duplicate_titles(monkeypatch) -> None:
    temp_artifacts_dir = _local_temp_dir("duplicate-name") / "scenarios"
    monkeypatch.setattr(storage, "ARTIFACTS_DIR", temp_artifacts_dir)

    with TestClient(app) as client:
        payload = load_fixture("bridge_reconnect.json")
        duplicate_title_payload = load_fixture("bridge_reconnect.json")
        duplicate_title_payload["metadata"]["scenario_id"] = "incoming-different-id"

        first_save = client.post("/api/scenarios", json=payload)
        second_save = client.post("/api/scenarios", json=duplicate_title_payload)

        assert first_save.status_code == 200
        assert second_save.status_code == 200

        first = first_save.json()
        second = second_save.json()

        assert first["scenario_id"] == "bridge-reconnect"
        assert second["scenario_id"] == "bridge-reconnect-2"
        assert second["title"] == "Bridge Reconnect 2"

        scenarios = client.get("/api/scenarios").json()
        assert [item["scenario_id"] for item in scenarios] == [
            "bridge-reconnect",
            "bridge-reconnect-2",
        ]
