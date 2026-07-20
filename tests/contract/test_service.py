"""API contract tests over representative captured Arr payload shapes
(field structure per research/arr-webhook-schemas.md, camelCase as Arr
sends them). No ffmpeg -- the API never touches media.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from censorr.config.schema import ResolvedConfig
from censorr.service.app import create_app


def make_client(tmp_path: Path, **cfg_overrides: Any) -> TestClient:
    service = {"queue_path": str(tmp_path / "queue"), **cfg_overrides.pop("service", {})}
    cfg = ResolvedConfig(service=service, **cfg_overrides)
    return TestClient(create_app(cfg))


def radarr_download_payload(
    *, path: str = "/data/media/movies/Test Movie (2024)/Test Movie (2024).mkv",
    tags: list[str] | None = None,
    is_upgrade: bool = False,
    deleted_files: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "eventType": "Download",
        "instanceName": "Radarr",
        "movie": {
            "id": 1,
            "title": "Test Movie",
            "year": 2024,
            "folderPath": "/data/media/movies/Test Movie (2024)",
            "tags": tags if tags is not None else ["censorr"],
        },
        "movieFile": {"id": 10, "path": path, "relativePath": Path(path).name},
        "isUpgrade": is_upgrade,
        "deletedFiles": [
            {"id": 9, "path": p, "relativePath": Path(p).name} for p in (deleted_files or [])
        ],
    }


def sonarr_download_payload(
    *, path: str = "/data/media/tv/Test Show/Season 01/Test Show - s01e01.mkv",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "eventType": "Download",
        "instanceName": "Sonarr",
        "series": {
            "id": 5,
            "title": "Test Show",
            "path": "/data/media/tv/Test Show",
            "tags": tags if tags is not None else ["censorr"],
        },
        "episodeFile": {"id": 20, "path": path, "relativePath": Path(path).name},
        "isUpgrade": False,
        "deletedFiles": [],
    }


def queued_entries(tmp_path: Path) -> list[dict[str, Any]]:
    incoming = tmp_path / "queue" / "incoming"
    return [json.loads(p.read_text()) for p in sorted(incoming.glob("*.json"))]


class TestWebhookEvents:
    def test_test_event_returns_ok_without_enqueue(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)

        response = client.post("/webhook/radarr", json={"eventType": "Test"})

        assert response.status_code == 202
        assert response.json() == {"status": "ok"}
        assert queued_entries(tmp_path) == []

    def test_unknown_event_ignored(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)

        response = client.post("/webhook/radarr", json={"eventType": "Grab"})

        assert response.json() == {"status": "ignored", "reason": "unhandled_event"}
        assert queued_entries(tmp_path) == []

    def test_download_movie_enqueues(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)

        response = client.post("/webhook/radarr", json=radarr_download_payload())

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "queued"
        entries = queued_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["job"]["media_type_hint"] == "movie"
        assert entries[0]["job"]["submitted_by"] == "webhook:radarr"

    def test_download_episode_enqueues(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)

        response = client.post("/webhook/sonarr", json=sonarr_download_payload())

        assert response.status_code == 202
        entries = queued_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["job"]["media_type_hint"] == "episode"

    def test_upgrade_carries_deleted_files(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)
        payload = radarr_download_payload(
            is_upgrade=True,
            deleted_files=["/data/media/movies/Test Movie (2024)/Test Movie (2024) OLD.mkv"],
        )

        client.post("/webhook/radarr", json=payload)

        entry = queued_entries(tmp_path)[0]
        assert entry["job"]["is_upgrade"] is True
        assert entry["job"]["deleted_files"] == [
            "/data/media/movies/Test Movie (2024)/Test Movie (2024) OLD.mkv"
        ]

    def test_missing_path_ignored(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)
        payload = radarr_download_payload()
        del payload["movieFile"]

        response = client.post("/webhook/radarr", json=payload)

        assert response.json() == {"status": "ignored", "reason": "missing_path"}


class TestTagGating:
    def test_untagged_movie_ignored_by_default(self, tmp_path: Path) -> None:
        # Q18: require_tags defaults to ["censorr"] -- untagged items are
        # never processed by webhooks.
        client = make_client(tmp_path)

        response = client.post("/webhook/radarr", json=radarr_download_payload(tags=[]))

        assert response.json() == {"status": "ignored", "reason": "not_tagged"}
        assert queued_entries(tmp_path) == []

    def test_untagged_series_ignored_by_default(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)

        response = client.post("/webhook/sonarr", json=sonarr_download_payload(tags=[]))

        assert response.json() == {"status": "ignored", "reason": "not_tagged"}

    def test_empty_require_tags_disables_gating(self, tmp_path: Path) -> None:
        client = make_client(tmp_path, service={"require_tags": []})

        response = client.post("/webhook/radarr", json=radarr_download_payload(tags=[]))

        assert response.json()["status"] == "queued"

    def test_custom_require_tag_honored(self, tmp_path: Path) -> None:
        client = make_client(tmp_path, service={"require_tags": ["family"]})

        gated = client.post("/webhook/radarr", json=radarr_download_payload(tags=["censorr"]))
        passed = client.post("/webhook/radarr", json=radarr_download_payload(tags=["family"]))

        assert gated.json()["reason"] == "not_tagged"
        assert passed.json()["status"] == "queued"


class TestSecret:
    def test_bad_token_rejected(self, tmp_path: Path) -> None:
        client = make_client(tmp_path, service={"secret": "shh"})

        response = client.post("/webhook/radarr", json=radarr_download_payload())

        assert response.status_code == 403

    def test_query_token_accepted(self, tmp_path: Path) -> None:
        client = make_client(tmp_path, service={"secret": "shh"})

        response = client.post("/webhook/radarr?token=shh", json=radarr_download_payload())

        assert response.status_code == 202

    def test_header_secret_accepted(self, tmp_path: Path) -> None:
        client = make_client(tmp_path, service={"secret": "shh"})

        response = client.post(
            "/webhook/radarr",
            json=radarr_download_payload(),
            headers={"X-Webhook-Secret": "shh"},
        )

        assert response.status_code == 202


class TestPathMapping:
    def test_unmapped_path_ignored(self, tmp_path: Path) -> None:
        client = make_client(tmp_path, service={"path_map": {"/data/media": "/data/media"}})
        payload = radarr_download_payload(path="/somewhere/else/Movie.mkv")

        response = client.post("/webhook/radarr", json=payload)

        assert response.json() == {"status": "ignored", "reason": "unmapped_path"}

    def test_prefix_remapped_into_worker_view(self, tmp_path: Path) -> None:
        client = make_client(tmp_path, service={"path_map": {"/data/media": "/mnt/storage"}})

        client.post("/webhook/radarr", json=radarr_download_payload())

        entry = queued_entries(tmp_path)[0]
        assert entry["job"]["source"].startswith("/mnt/storage/movies/")

    def test_empty_map_passes_through(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)

        client.post("/webhook/radarr", json=radarr_download_payload())

        entry = queued_entries(tmp_path)[0]
        assert entry["job"]["source"].startswith("/data/media/movies/")


class TestPresetResolution:
    def test_query_param_wins(self, tmp_path: Path) -> None:
        client = make_client(tmp_path, arr_tag_presets={"censorr-strict": "strict"})
        payload = radarr_download_payload(tags=["censorr", "censorr-strict"])

        client.post("/webhook/radarr?preset=override", json=payload)

        assert queued_entries(tmp_path)[0]["job"]["preset"] == "override"

    def test_tag_map_applies(self, tmp_path: Path) -> None:
        client = make_client(tmp_path, arr_tag_presets={"censorr-strict": "strict"})
        payload = radarr_download_payload(tags=["censorr", "censorr-strict"])

        client.post("/webhook/radarr", json=payload)

        assert queued_entries(tmp_path)[0]["job"]["preset"] == "strict"

    def test_media_type_default_only_when_defined(self, tmp_path: Path) -> None:
        without_presets = make_client(tmp_path)
        without_presets.post("/webhook/radarr", json=radarr_download_payload())
        assert queued_entries(tmp_path)[0]["job"]["preset"] is None

        with_presets = make_client(tmp_path / "b", preset_names=["movies", "tv"])
        with_presets.post("/webhook/radarr", json=radarr_download_payload())
        assert queued_entries(tmp_path / "b")[0]["job"]["preset"] == "movies"


class TestJobsApi:
    def test_submit_and_fetch_job(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)

        submitted = client.post("/jobs", json={"path": "/data/media/movies/M/M.mkv"})
        assert submitted.status_code == 202
        job_id = submitted.json()["job_id"]

        # No record until a worker touches it -> 404 is the honest answer.
        assert client.get(f"/jobs/{job_id}").status_code == 404

        record = {
            "job": {"id": job_id, "source": "/data/media/movies/M/M.mkv"},
            "status": "running",
            "progress": 0.5,
            "created_at": "2026-07-18T00:00:00+00:00",
        }
        records_dir = tmp_path / "queue" / "records"
        records_dir.mkdir(parents=True, exist_ok=True)
        (records_dir / f"{job_id}.json").write_text(json.dumps(record))

        fetched = client.get(f"/jobs/{job_id}")
        assert fetched.status_code == 200
        assert fetched.json()["progress"] == 0.5

    def test_list_jobs_filters_by_status(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)
        records_dir = tmp_path / "queue" / "records"
        records_dir.mkdir(parents=True, exist_ok=True)
        for i, status in enumerate(["done", "failed", "done"]):
            record = {"job": {"id": f"j{i}"}, "status": status, "created_at": f"2026-07-1{i}"}
            (records_dir / f"j{i}.json").write_text(json.dumps(record))

        all_jobs = client.get("/jobs").json()
        done_jobs = client.get("/jobs?status=done").json()

        assert len(all_jobs) == 3
        assert len(done_jobs) == 2

    def test_healthz(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)

        assert client.get("/healthz").json() == {"status": "ok"}

    def test_status_counters(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)
        client.post("/jobs", json={"path": "/data/media/movies/M/M.mkv"})

        body = client.get("/status").json()

        assert body["queue_depth"] == 1
        assert body["processing"] == 0
        assert "version" in body
        assert body["presets"] == []

    def test_status_lists_configured_presets(self, tmp_path: Path) -> None:
        client = make_client(tmp_path, preset_names=["movies", "strict", "tv"])

        assert client.get("/status").json()["presets"] == ["movies", "strict", "tv"]

    def test_openapi_docs_render(self, tmp_path: Path) -> None:
        client = make_client(tmp_path)

        response = client.get("/openapi.json")

        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/webhook/radarr" in paths
        assert "/webhook/sonarr" in paths
        assert "/jobs" in paths


@pytest.mark.parametrize("endpoint", ["/webhook/radarr", "/webhook/sonarr"])
def test_malformed_payload_rejected(tmp_path: Path, endpoint: str) -> None:
    client = make_client(tmp_path)

    response = client.post(endpoint, json={"noEventType": True})

    assert response.status_code == 422
