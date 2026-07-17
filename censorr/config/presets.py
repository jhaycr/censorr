from typing import Any


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge `overlay` onto `base`, recursing into nested dicts. `overlay` wins."""
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def apply_preset(base: dict[str, Any], presets: dict[str, Any], name: str | None) -> dict[str, Any]:
    """Overlay the named preset's section onto `base`. No-op if `name` is None."""
    if name is None:
        return base
    preset_data = presets.get(name)
    if preset_data is None:
        raise KeyError(f"unknown preset: {name!r}")
    return deep_merge(base, preset_data)
