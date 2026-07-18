import hashlib
import json
from pathlib import Path

from censorr import __version__
from censorr.config.schema import ResolvedConfig
from censorr.detect.wordlist import WordList


def compute_fingerprint(
    *, source_size: int, source_mtime: float, cfg: ResolvedConfig, wordlist: WordList
) -> str:
    """R10: source identity (size+mtime) + resolved settings + wordlist
    content hash + app version. `source_path` is deliberately excluded so
    host-vs-container path views agree.
    """
    payload = {
        "source_size": source_size,
        "source_mtime": source_mtime,
        "settings": cfg.model_dump(mode="json"),
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
