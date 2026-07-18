import hashlib
import json
from pathlib import Path

from censorr import __version__
from censorr.config.schema import ResolvedConfig
from censorr.detect.wordlist import WordList, load_wordlist, merge_wordlists
from censorr.media.probe import probe
from censorr.naming.models import MediaType, NamingPlan
from censorr.naming.plex import plan_names


def resolve_wordlist(cfg: ResolvedConfig) -> WordList:
    bundled = load_wordlist()
    user = load_wordlist(cfg.detect.wordlist) if cfg.detect.wordlist else None
    return merge_wordlists(bundled, user)


def compute_fingerprint(
    *, source_size: int, source_mtime: float, cfg: ResolvedConfig, wordlist: WordList
) -> str:
    """R10: source identity (size+mtime) + resolved settings + wordlist
    content hash + app version. `source_path` is deliberately excluded so
    host-vs-container path views agree; so are `service` settings and
    `preset_names` -- queue paths/TTLs/defined-preset lists can't affect
    output content, and including them would force a pointless full-library
    reprocess after e.g. moving the queue directory.
    """
    payload = {
        "source_size": source_size,
        "source_mtime": source_mtime,
        "settings": cfg.model_dump(mode="json", exclude={"service", "preset_names"}),
        "wordlist_content_hash": wordlist.content_hash,
        "app_version": __version__,
    }
    data = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()


def fingerprint_for_source(source: Path, *, cfg: ResolvedConfig, wordlist: WordList) -> str:
    stat = source.stat()
    return compute_fingerprint(
        source_size=stat.st_size, source_mtime=stat.st_mtime, cfg=cfg, wordlist=wordlist
    )


def check_skip(
    source: Path, media_type: MediaType, *, cfg: ResolvedConfig, wordlist: WordList
) -> tuple[bool, NamingPlan]:
    """R10 skip-check: cheap and pure except for reading the expected
    output's own metadata tag (no source processing). `plan_names` ->
    expected output exists? -> read CENSORR_FINGERPRINT -> compare.
    """
    naming_plan = plan_names(source, media_type, cfg.naming, language=cfg.subtitles.language)
    if not naming_plan.video_path.is_file():
        return False, naming_plan

    existing_fingerprint = probe(naming_plan.video_path).format_tags.get("CENSORR_FINGERPRINT")
    if existing_fingerprint is None:
        return False, naming_plan

    current_fingerprint = fingerprint_for_source(source, cfg=cfg, wordlist=wordlist)
    return existing_fingerprint == current_fingerprint, naming_plan
