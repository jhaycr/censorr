import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError

from censorr.config.load import load_config
from censorr.service.logging import log_event
from censorr.service.ui import UI_HTML

router = APIRouter()


class ConfigFileBody(BaseModel):
    content: str


@router.get("/", response_class=HTMLResponse)
@router.get("/ui", response_class=HTMLResponse)
def ui_page() -> str:
    return UI_HTML


def _config_path(request: Request) -> Path:
    path: Path | None = request.app.state.config_path
    if path is None:
        raise HTTPException(status_code=404, detail="no config file configured")
    return path


@router.get("/config/file")
def get_config_file(request: Request) -> dict[str, str]:
    path = _config_path(request)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"config file missing: {path}")
    return {"path": str(path), "content": path.read_text()}


@router.put("/config/file")
def put_config_file(body: ConfigFileBody, request: Request) -> dict[str, str]:
    """Validate-then-write: the candidate TOML must parse and satisfy the
    schema before it can touch the real file; the running service reloads
    immediately so gating/path-map changes apply to the next webhook.
    Workers re-resolve config per job, so they pick it up too (queue-path
    and port changes still need a restart)."""
    path = _config_path(request)

    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as tmp:
        tmp.write(body.content)
        candidate = Path(tmp.name)
    try:
        load_config(config_path=candidate)
    except (ValidationError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid config: {exc}") from exc
    finally:
        candidate.unlink(missing_ok=True)

    tmp_target = path.with_suffix(".toml.tmp")
    tmp_target.write_text(body.content)
    os.replace(tmp_target, path)

    request.app.state.cfg = load_config(config_path=path)
    log_event("config_updated", path=str(path))
    return {"status": "saved", "path": str(path)}
