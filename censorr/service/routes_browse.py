from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from censorr.config.schema import ResolvedConfig
from censorr.pipeline.library import VIDEO_EXTENSIONS

router = APIRouter()

_MAX_ENTRIES = 500


def _browse_roots(cfg: ResolvedConfig) -> list[Path]:
    return [Path(root) for root in cfg.service.browse_roots]


def _resolve_inside_roots(candidate: str, roots: list[Path]) -> Path:
    """Path-traversal guard: the resolved path must live under a configured
    browse root. Anything else (.., symlink escapes, absolute paths outside)
    is rejected before any filesystem listing happens."""
    resolved = Path(candidate).resolve()
    for root in roots:
        if resolved == root or resolved.is_relative_to(root):
            return resolved
    raise HTTPException(status_code=403, detail="path outside the configured browse roots")


@router.get("/browse")
def browse(request: Request, path: str | None = Query(default=None)) -> dict[str, object]:
    """List directories and video files at `path`, confined to
    service.browse_roots (Q19: serve mounts sources read-only for this).
    No path -> list the roots themselves."""
    cfg: ResolvedConfig = request.app.state.cfg
    roots = _browse_roots(cfg)

    if path is None:
        return {
            "path": None,
            "parent": None,
            "dirs": [str(r) for r in roots if r.is_dir()],
            "files": [],
        }

    target = _resolve_inside_roots(path, roots)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail=f"not a directory: {target}")

    dirs: list[str] = []
    files: list[str] = []
    for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            dirs.append(entry.name)
        elif entry.suffix.lower() in VIDEO_EXTENSIONS:
            files.append(entry.name)
        if len(dirs) + len(files) >= _MAX_ENTRIES:
            break

    at_root = any(target == r for r in roots)
    return {
        "path": str(target),
        "parent": None if at_root else str(target.parent),
        "dirs": dirs,
        "files": files,
    }
