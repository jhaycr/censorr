import re
from pathlib import Path

from censorr.config.schema import ResolvedConfig
from censorr.media.probe import probe
from censorr.naming.plex import classify, plan_names

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov"}

# R7: Plex extras are never processed.
PLEX_EXTRA_DIRS = {"trailers", "behind the scenes", "featurettes"}

_EDITION_TAG_RE = re.compile(r"\{edition-([^}]+)\}", re.IGNORECASE)


def _is_plex_extra(path: Path, root: Path) -> bool:
    for parent in path.parents:
        if parent == root:
            break
        if parent.name.lower() in PLEX_EXTRA_DIRS:
            return True
    return "-sample" in path.stem.lower()


def _name_carries_edition_tag(path: Path, edition_tag: str) -> bool:
    match = _EDITION_TAG_RE.search(path.name)
    return match is not None and edition_tag.lower() in match.group(1).lower()


def _metadata_carries_fingerprint(path: Path) -> bool:
    try:
        return "CENSORR_FINGERPRINT" in probe(path).format_tags
    except Exception:  # noqa: BLE001 -- unreadable/corrupt media is not a censorr output
        return False


def is_censorr_output(path: Path, edition_tag: str) -> bool:
    """R7: a Censorr output is any file whose name contains the configured
    edition tag or whose metadata carries CENSORR_FINGERPRINT -- ingestion
    must never re-censor an output."""
    return _name_carries_edition_tag(path, edition_tag) or _metadata_carries_fingerprint(path)


def find_reprocess_candidates(root: Path, cfg: ResolvedConfig) -> list[Path]:
    """Walk `root` for source video files eligible for *re*processing: sources
    that were already censored, i.e. an existing Censorr output maps back to
    them. Skips Censorr outputs and Plex extras.

    Reprocessing refreshes what was processed before -- it is *not* first-time
    bulk censoring, so a source with no existing output is left alone (that is
    the webhook/`process` path's job, and it must not silently censor untagged
    library content). Fingerprint staleness is the caller's per-file check
    (check_skip); this only builds the worklist.
    """
    candidates = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if _is_plex_extra(path, root):
            continue
        if is_censorr_output(path, cfg.naming.edition_tag):
            continue
        plan = plan_names(path, classify(path), cfg.naming, language=cfg.subtitles.language)
        if not plan.video_path.is_file():
            continue  # never produced an output -> not a reprocess target
        candidates.append(path)
    return candidates


def _strip_censorr_from_edition(name: str, edition_tag: str) -> str | None:
    """Reverse of plan_names' movie naming: remove the Censorr edition tag
    (or just the Censorr part of a combined tag), returning the source
    filename. None when the name carries no Censorr tag."""
    match = _EDITION_TAG_RE.search(name)
    if match is None or edition_tag.lower() not in match.group(1).lower():
        return None
    remaining = re.sub(rf"\s*{re.escape(edition_tag)}\s*", " ", match.group(1), flags=re.IGNORECASE)
    remaining = remaining.strip()
    if remaining:
        replacement = f"{{edition-{remaining}}}"
        source_name = name[: match.start()] + replacement + name[match.end() :]
    else:
        source_name = name[: match.start()] + name[match.end() :]
    return re.sub(r"\s+", " ", source_name).replace(" .", ".").strip()


def derive_source_for_output(output: Path, clean_root: Path, cfg: ResolvedConfig) -> Path | None:
    """Best-effort reverse of plan_names (Q18: movies and episodes both
    live under a clean root). The source root comes from removing the
    clean root's `-clean` suffix; movie outputs additionally strip the
    Censorr edition tag from the filename. None when no reverse mapping
    exists -- reconcile must then leave the file alone."""
    if not clean_root.name.endswith("-clean"):
        return None
    source_root = clean_root.with_name(clean_root.name[: -len("-clean")])
    candidate = source_root / output.relative_to(clean_root)

    source_name = _strip_censorr_from_edition(output.name, cfg.naming.edition_tag)
    if source_name is not None:
        return candidate.with_name(source_name)
    return candidate


def find_orphaned_outputs(clean_root: Path, cfg: ResolvedConfig) -> list[Path]:
    """R7 reconcile: Censorr outputs under `clean_root` whose source no
    longer exists (heals rename/delete drift). Files with no derivable
    source mapping are never treated as orphans."""
    orphans = []
    for path in sorted(clean_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if not is_censorr_output(path, cfg.naming.edition_tag):
            continue
        source = derive_source_for_output(path, clean_root, cfg)
        if source is not None and not source.exists():
            orphans.append(path)
    return orphans


def delete_output_with_sidecars(output: Path) -> list[Path]:
    """Delete a clean output plus any sidecar subtitles sharing its stem."""
    removed = []
    for sidecar in sorted(output.parent.glob(f"{output.stem}.*.srt")):
        sidecar.unlink()
        removed.append(sidecar)
    output.unlink()
    removed.append(output)
    return removed
