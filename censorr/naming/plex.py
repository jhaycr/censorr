import re
from pathlib import Path

from censorr.config.schema import NamingConfig
from censorr.naming.models import MediaType, MediaTypeHint, NamingPlan
from censorr.pipeline.errors import JobValidationError

_EPISODE_PATTERNS = [
    re.compile(r"S\d{1,2}E\d{1,2}", re.IGNORECASE),
    re.compile(r"Season\s*\d+.*Episode\s*\d+", re.IGNORECASE),
    re.compile(r"\d{1,2}x\d{1,2}"),
]
_EDITION_TAG_RE = re.compile(r"\{edition-([^}]+)\}", re.IGNORECASE)
_YEAR_RE = re.compile(r"\([12]\d{3}\)")
_SEASON_DIR_RE = re.compile(r"^(season\s*\d+|specials)$", re.IGNORECASE)

_CENSORED_TITLE = "English (Censored)"


def classify(source: Path, hint: MediaTypeHint | None = None) -> MediaType:
    """Arr hint wins over filename regex (per implications-for-v2 in the naming research)."""
    if hint is not None:
        return MediaType(hint.value)
    name = source.stem
    if any(pattern.search(name) for pattern in _EPISODE_PATTERNS):
        return MediaType.EPISODE
    return MediaType.MOVIE


def _track_titles() -> dict[str, str]:
    return {"audio": _CENSORED_TITLE, "subtitle": _CENSORED_TITLE}


def _sidecar_path(video_path: Path, cfg: NamingConfig, language: str) -> Path:
    token_part = f".{cfg.sidecar_token}" if cfg.sidecar_token else ""
    return video_path.with_name(f"{video_path.stem}.{language}{token_part}.srt")


def _parse_existing_edition(stem: str) -> tuple[str, str | None]:
    match = _EDITION_TAG_RE.search(stem)
    if not match:
        return stem, None
    base = _EDITION_TAG_RE.sub("", stem).strip()
    base = re.sub(r"\s+", " ", base)
    return base, match.group(1)


def derive_movie_clean_root(source: Path) -> Path:
    """Q18 (mirrors R5's tv derivation): the movie's own folder is the
    file's parent, the movies library root is its parent, clean root =
    <root>-clean. Sources sitting flat in the library root (no per-movie
    folder) can't be derived -- set naming.movie_clean_root explicitly.
    """
    movie_dir = source.parent
    root = movie_dir.parent
    if not root.name:
        raise JobValidationError(
            f"source path too shallow to derive a movie clean root: {source} "
            "(set naming.movie_clean_root explicitly)"
        )
    return root.with_name(root.name + "-clean")


def _plan_movie(source: Path, cfg: NamingConfig, language: str) -> NamingPlan:
    base_stem, existing_edition = _parse_existing_edition(source.stem)
    # Plex allows one edition tag; combine so both facts survive (R4).
    tag_content = f"{existing_edition} {cfg.edition_tag}" if existing_edition else cfg.edition_tag

    year_match = _YEAR_RE.search(base_stem)
    if year_match:
        insert_at = year_match.end()
        new_stem = f"{base_stem[:insert_at]} {{edition-{tag_content}}}{base_stem[insert_at:]}"
    else:
        new_stem = f"{base_stem} {{edition-{tag_content}}}"
    new_stem = re.sub(r"\s+", " ", new_stem).strip()

    # Q18: movies land in a separate clean root (own-folder structure
    # mirrored) so a separate Plex library can gate access -- same-folder
    # editions are viewer-selectable and restrict nothing.
    clean_root = cfg.movie_clean_root or derive_movie_clean_root(source)
    video_path = clean_root / source.parent.name / f"{new_stem}{source.suffix}"
    if video_path == source:
        raise JobValidationError(f"planned output path equals source path: {source}")

    sidecar_paths = [_sidecar_path(video_path, cfg, language)] if cfg.write_sidecar else []

    return NamingPlan(
        video_path=video_path,
        sidecar_paths=sidecar_paths,
        edition_tag_applied=tag_content,
        track_titles=_track_titles(),
    )


def _find_show_and_season_dirs(source: Path) -> tuple[Path, Path | None]:
    current = source.parent
    while current != current.parent:
        if _SEASON_DIR_RE.match(current.name):
            return current.parent, current
        current = current.parent
    return source.parent, None


def derive_tv_clean_root(source: Path) -> Path:
    """R5: walk up to a Season N/Specials dir -> its parent is the show dir ->
    the show dir's parent is the library root -> clean root = <root>-clean.
    No season-like dir: show dir = file's parent, root = its parent.
    """
    show_dir, _season_dir = _find_show_and_season_dirs(source)
    root = show_dir.parent
    if not root.name:
        raise JobValidationError(
            f"source path too shallow to derive a TV clean root: {source} "
            "(set naming.tv_clean_root explicitly)"
        )
    return root.with_name(root.name + "-clean")


def _plan_episode(source: Path, cfg: NamingConfig, language: str) -> NamingPlan:
    clean_root = cfg.tv_clean_root or derive_tv_clean_root(source)
    show_dir, season_dir = _find_show_and_season_dirs(source)
    relative = (
        Path(show_dir.name) / season_dir.name / source.name
        if season_dir is not None
        else Path(show_dir.name) / source.name
    )
    video_path = clean_root / relative

    if video_path == source:
        raise JobValidationError(f"planned output path equals source path: {source}")

    sidecar_paths = [_sidecar_path(video_path, cfg, language)] if cfg.write_sidecar else []

    return NamingPlan(
        video_path=video_path,
        sidecar_paths=sidecar_paths,
        edition_tag_applied=None,
        track_titles=_track_titles(),
    )


def plan_names(
    source: Path, media_type: MediaType, cfg: NamingConfig, *, language: str = "en"
) -> NamingPlan:
    """PURE: no filesystem writes, no subprocess. Hard invariant: planned
    output path != source path, enforced in every branch (R4/R5)."""
    if media_type == MediaType.MOVIE:
        return _plan_movie(source, cfg, language)
    return _plan_episode(source, cfg, language)
