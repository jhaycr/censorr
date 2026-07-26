"""Contract tests for /browse: listing confined to browse_roots, with
path-traversal and outside-root requests rejected."""

from pathlib import Path

from fastapi.testclient import TestClient

from censorr.config.schema import ResolvedConfig
from censorr.service.app import create_app


def make_client(tmp_path: Path) -> tuple[TestClient, Path]:
    media = tmp_path / "media"
    (media / "tv" / "Show A" / "Season 01").mkdir(parents=True)
    (media / "tv" / "Show A" / "Season 01" / "ep1.mkv").write_bytes(b"x")
    (media / "tv" / "Show A" / "Season 01" / "notes.txt").write_bytes(b"x")
    (media / "tv" / ".hidden").mkdir()
    (tmp_path / "outside-secret.txt").write_bytes(b"x")
    cfg = ResolvedConfig(
        service={"queue_path": str(tmp_path / "queue"), "browse_roots": [str(media)]}
    )
    return TestClient(create_app(cfg)), media


class TestBrowse:
    def test_no_path_lists_roots(self, tmp_path: Path) -> None:
        client, media = make_client(tmp_path)

        body = client.get("/browse").json()

        assert body["dirs"] == [str(media)]
        assert body["parent"] is None

    def test_lists_dirs_and_video_files_only(self, tmp_path: Path) -> None:
        client, media = make_client(tmp_path)

        season = media / "tv" / "Show A" / "Season 01"
        body = client.get("/browse", params={"path": str(season)}).json()

        assert body["files"] == ["ep1.mkv"]  # notes.txt excluded
        assert body["dirs"] == []

    def test_hidden_entries_excluded(self, tmp_path: Path) -> None:
        client, media = make_client(tmp_path)

        body = client.get("/browse", params={"path": str(media / "tv")}).json()

        assert body["dirs"] == ["Show A"]

    def test_parent_navigation_stops_at_root(self, tmp_path: Path) -> None:
        client, media = make_client(tmp_path)

        at_show = client.get("/browse", params={"path": str(media / "tv")}).json()
        at_root = client.get("/browse", params={"path": str(media)}).json()

        assert at_show["parent"] == str(media)
        assert at_root["parent"] is None

    def test_traversal_rejected(self, tmp_path: Path) -> None:
        client, media = make_client(tmp_path)

        response = client.get("/browse", params={"path": f"{media}/tv/../../"})

        assert response.status_code == 403

    def test_outside_root_rejected(self, tmp_path: Path) -> None:
        client, _media = make_client(tmp_path)

        response = client.get("/browse", params={"path": str(tmp_path)})

        assert response.status_code == 403

    def test_missing_directory_404(self, tmp_path: Path) -> None:
        client, media = make_client(tmp_path)

        response = client.get("/browse", params={"path": str(media / "tv" / "nope")})

        assert response.status_code == 404


class TestBrowseLimit:
    """Large directories (a movie library easily exceeds 500 entries) are
    truncated honestly: `limit` raises the cap, `truncated` says when
    entries were dropped so the UI never silently hides the rest."""

    def make_wide_client(self, tmp_path: Path, entries: int) -> tuple[TestClient, Path]:
        media = tmp_path / "media"
        for i in range(entries):
            (media / f"Movie {i:04d} (2024)").mkdir(parents=True)
        cfg = ResolvedConfig(
            service={"queue_path": str(tmp_path / "queue"), "browse_roots": [str(media)]}
        )
        return TestClient(create_app(cfg)), media

    def test_default_limit_truncates_and_flags(self, tmp_path: Path) -> None:
        client, media = self.make_wide_client(tmp_path, 501)

        body = client.get("/browse", params={"path": str(media)}).json()

        assert len(body["dirs"]) == 500
        assert body["truncated"] is True

    def test_higher_limit_returns_everything(self, tmp_path: Path) -> None:
        client, media = self.make_wide_client(tmp_path, 501)

        body = client.get("/browse", params={"path": str(media), "limit": 10000}).json()

        assert len(body["dirs"]) == 501
        assert body["truncated"] is False

    def test_exactly_limit_entries_is_not_truncated(self, tmp_path: Path) -> None:
        client, media = self.make_wide_client(tmp_path, 3)

        body = client.get("/browse", params={"path": str(media), "limit": 3}).json()

        assert len(body["dirs"]) == 3
        assert body["truncated"] is False

    def test_limit_above_maximum_rejected(self, tmp_path: Path) -> None:
        client, media = self.make_wide_client(tmp_path, 1)

        response = client.get("/browse", params={"path": str(media), "limit": 10001})

        assert response.status_code == 422
