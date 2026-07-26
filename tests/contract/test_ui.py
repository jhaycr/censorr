"""Contract tests for the web UI page."""

from pathlib import Path

from fastapi.testclient import TestClient

from censorr.config.schema import ResolvedConfig
from censorr.service.app import create_app


def make_client(tmp_path: Path, *, with_config: bool = True) -> tuple[TestClient, Path | None]:
    config_path: Path | None = None
    if with_config:
        config_path = tmp_path / "censorr.toml"
        config_path.write_text(f'[service]\nqueue_path = "{tmp_path / "queue"}"\n')
    cfg = ResolvedConfig(service={"queue_path": str(tmp_path / "queue")})
    return TestClient(create_app(cfg, config_path)), config_path


class TestUiPage:
    def test_ui_served_at_root_and_ui(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)

        for path in ("/", "/ui"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")
            assert "censorr" in response.text

    def test_ui_page_is_self_contained(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)

        html = client.get("/ui").text

        # No external scripts/styles/fonts -- the page must work on a LAN
        # with no internet and no build step.
        assert "http://" not in html.replace("http://192", "KNOWN")  # no external refs
        assert "https://" not in html
        assert "<script src" not in html


class TestConfigEndpointsRemoved:
    """Config is file-managed only: the service must expose no read or write
    access to it over HTTP (the UI pane and its endpoints were removed)."""

    def test_config_file_endpoints_gone(self, tmp_path: Path) -> None:
        client, config_path = make_client(tmp_path)
        original = config_path.read_text()  # type: ignore[union-attr]

        assert client.get("/config/file").status_code == 404
        assert client.put("/config/file", json={"content": "[detect]\n"}).status_code in (404, 405)
        assert config_path.read_text() == original  # type: ignore[union-attr]
