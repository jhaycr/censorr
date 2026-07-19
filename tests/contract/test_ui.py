"""Contract tests for the web UI page and its config-file endpoints."""

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


class TestConfigFile:
    def test_get_returns_current_content(self, tmp_path: Path) -> None:
        client, config_path = make_client(tmp_path)

        response = client.get("/config/file")

        assert response.status_code == 200
        assert response.json()["content"] == config_path.read_text()  # type: ignore[union-attr]

    def test_get_404_when_no_config_configured(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path, with_config=False)

        assert client.get("/config/file").status_code == 404

    def test_put_valid_config_persists_and_reloads(self, tmp_path: Path) -> None:
        client, config_path = make_client(tmp_path)
        new_content = (
            f'[service]\nqueue_path = "{tmp_path / "queue"}"\nrequire_tags = []\n'
            "[detect]\nbuffer_s = 0.5\n"
        )

        response = client.put("/config/file", json={"content": new_content})

        assert response.status_code == 200
        assert config_path.read_text() == new_content  # type: ignore[union-attr]
        # Live reload: the running app now carries the new values.
        assert client.app.state.cfg.detect.buffer_s == 0.5  # type: ignore[attr-defined]
        assert client.app.state.cfg.service.require_tags == []  # type: ignore[attr-defined]

    def test_put_invalid_toml_rejected_and_file_untouched(self, tmp_path: Path) -> None:
        client, config_path = make_client(tmp_path)
        original = config_path.read_text()  # type: ignore[union-attr]

        response = client.put("/config/file", json={"content": "[detect\nbroken = "})

        assert response.status_code == 422
        assert config_path.read_text() == original  # type: ignore[union-attr]

    def test_put_unknown_key_rejected(self, tmp_path: Path) -> None:
        client, config_path = make_client(tmp_path)
        original = config_path.read_text()  # type: ignore[union-attr]

        response = client.put(
            "/config/file", json={"content": "[detect]\nnot_a_real_setting = 1\n"}
        )

        assert response.status_code == 422
        assert "invalid config" in response.json()["detail"]
        assert config_path.read_text() == original  # type: ignore[union-attr]
