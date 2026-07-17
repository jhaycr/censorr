import tomllib
from pathlib import Path
from typing import Any

from censorr.config.presets import apply_preset, deep_merge
from censorr.config.schema import RELATIVE_PATH_FIELDS, ResolvedConfig


def discover_config_path(explicit: Path | None) -> Path | None:
    """--config path > ./censorr.toml > ~/.config/censorr/censorr.toml > none."""
    if explicit is not None:
        if not explicit.is_file():
            raise FileNotFoundError(f"config file not found: {explicit}")
        return explicit.resolve()
    cwd_config = Path("censorr.toml").resolve()
    if cwd_config.is_file():
        return cwd_config
    user_config = Path("~/.config/censorr/censorr.toml").expanduser()
    if user_config.is_file():
        return user_config
    return None


def _resolve_relative_paths(data: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    for section, field in RELATIVE_PATH_FIELDS:
        section_data = data.get(section)
        if not isinstance(section_data, dict):
            continue
        value = section_data.get(field)
        if isinstance(value, str) and not Path(value).is_absolute():
            section_data[field] = str(base_dir / value)
    return data


def load_config(
    config_path: Path | None = None,
    preset: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> ResolvedConfig:
    """Resolve config once: CLI explicit > preset > file > built-in defaults."""
    found_path = discover_config_path(config_path)
    raw: dict[str, Any] = {}
    if found_path is not None:
        with found_path.open("rb") as f:
            raw = tomllib.load(f)

    presets = raw.get("presets", {})
    base = {k: v for k, v in raw.items() if k != "presets"}

    merged = apply_preset(base, presets, preset)
    base_dir = found_path.parent if found_path is not None else Path.cwd()
    merged = _resolve_relative_paths(merged, base_dir)

    if overrides:
        merged = deep_merge(merged, overrides)

    merged["preset"] = preset
    return ResolvedConfig.model_validate(merged)
