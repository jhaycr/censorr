from pathlib import Path

import pytest
from pydantic import ValidationError

from censorr.config.load import discover_config_path, load_config
from censorr.config.schema import ResolvedConfig


def write_toml(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def test_absent_file_is_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    cfg = load_config()

    assert isinstance(cfg, ResolvedConfig)
    assert cfg.detect.buffer_s == 0.2
    assert cfg.subtitles.language == "en"


def test_empty_file_is_valid(tmp_path: Path) -> None:
    config_path = write_toml(tmp_path / "censorr.toml", "")

    cfg = load_config(config_path=config_path)

    assert cfg.detect.fuzzy_threshold == 85


def test_explicit_config_path_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(config_path=tmp_path / "nope.toml")


def test_invalid_keys_rejected(tmp_path: Path) -> None:
    config_path = write_toml(
        tmp_path / "censorr.toml",
        "[detect]\nnot_a_real_field = 1\n",
    )

    with pytest.raises(ValidationError):
        load_config(config_path=config_path)


def test_invalid_top_level_section_rejected(tmp_path: Path) -> None:
    config_path = write_toml(tmp_path / "censorr.toml", "[not_a_section]\nx = 1\n")

    with pytest.raises(ValidationError):
        load_config(config_path=config_path)


def test_file_overrides_defaults(tmp_path: Path) -> None:
    config_path = write_toml(
        tmp_path / "censorr.toml",
        "[detect]\nbuffer_s = 0.5\n",
    )

    cfg = load_config(config_path=config_path)

    assert cfg.detect.buffer_s == 0.5
    assert cfg.detect.fuzzy_threshold == 85  # untouched field keeps its default


def test_preset_overlay_wins_over_file_base(tmp_path: Path) -> None:
    config_path = write_toml(
        tmp_path / "censorr.toml",
        """
        [detect]
        buffer_s = 0.5

        [presets.movies.detect]
        buffer_s = 1.0
        """,
    )

    base_cfg = load_config(config_path=config_path)
    movies_cfg = load_config(config_path=config_path, preset="movies")

    assert base_cfg.detect.buffer_s == 0.5
    assert movies_cfg.detect.buffer_s == 1.0
    assert movies_cfg.preset == "movies"


def test_preset_only_overrides_its_own_fields(tmp_path: Path) -> None:
    config_path = write_toml(
        tmp_path / "censorr.toml",
        """
        [subtitles]
        language = "en"
        mute_captions = false

        [presets.tv.subtitles]
        language = "en"
        """,
    )

    cfg = load_config(config_path=config_path, preset="tv")

    assert cfg.subtitles.mute_captions is False  # not touched by the preset


def test_unknown_preset_raises(tmp_path: Path) -> None:
    config_path = write_toml(tmp_path / "censorr.toml", "[presets.movies]\n")

    with pytest.raises(KeyError):
        load_config(config_path=config_path, preset="does-not-exist")


def test_cli_override_wins_over_preset_and_file(tmp_path: Path) -> None:
    config_path = write_toml(
        tmp_path / "censorr.toml",
        """
        [detect]
        buffer_s = 0.5

        [presets.movies.detect]
        buffer_s = 1.0
        """,
    )

    cfg = load_config(
        config_path=config_path,
        preset="movies",
        overrides={"detect": {"buffer_s": 2.0}},
    )

    assert cfg.detect.buffer_s == 2.0


def test_relative_wordlist_path_resolves_against_config_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "nested"
    config_dir.mkdir()
    config_path = write_toml(
        config_dir / "censorr.toml",
        '[detect]\nwordlist = "mywords.json"\n',
    )

    cfg = load_config(config_path=config_path)

    assert cfg.detect.wordlist == config_dir / "mywords.json"


def test_absolute_wordlist_path_untouched(tmp_path: Path) -> None:
    config_path = write_toml(
        tmp_path / "censorr.toml",
        '[detect]\nwordlist = "/abs/words.json"\n',
    )

    cfg = load_config(config_path=config_path)

    assert cfg.detect.wordlist == Path("/abs/words.json")


def test_arr_tag_presets_and_service_pass_through(tmp_path: Path) -> None:
    config_path = write_toml(
        tmp_path / "censorr.toml",
        """
        [service]
        secret = "shh"

        [arr_tag_presets]
        censorr-strict = "strict"
        """,
    )

    cfg = load_config(config_path=config_path)

    assert cfg.service.secret == "shh"  # noqa: S105 -- test fixture value, not a credential
    assert cfg.arr_tag_presets == {"censorr-strict": "strict"}


def test_discover_config_path_prefers_explicit(tmp_path: Path) -> None:
    explicit = write_toml(tmp_path / "explicit.toml", "")

    assert discover_config_path(explicit) == explicit


def test_discover_config_path_falls_back_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    cwd_config = write_toml(tmp_path / "censorr.toml", "")

    assert discover_config_path(None) == cwd_config


def test_discover_config_path_falls_back_to_user_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_cwd = tmp_path / "cwd"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)
    home = tmp_path / "home"
    (home / ".config" / "censorr").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    user_config = write_toml(home / ".config" / "censorr" / "censorr.toml", "")

    assert discover_config_path(None) == user_config


def test_discover_config_path_none_when_nothing_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert discover_config_path(None) is None


def test_resolved_config_is_frozen(tmp_path: Path) -> None:
    cfg = load_config(config_path=write_toml(tmp_path / "censorr.toml", ""))

    with pytest.raises(ValidationError):
        cfg.detect = cfg.detect.model_copy(update={"buffer_s": 9.9})  # type: ignore[misc]
