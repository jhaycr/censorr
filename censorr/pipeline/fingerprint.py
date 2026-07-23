import hashlib
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from censorr import __version__
from censorr.config.schema import ResolvedConfig
from censorr.detect.wordlist import WordList, load_wordlist, merge_wordlists
from censorr.media.probe import probe
from censorr.naming.models import MediaType, NamingPlan
from censorr.naming.plex import plan_names
from censorr.pipeline.errors import CensorrError

if TYPE_CHECKING:
    from censorr.pipeline.context import PipelineContext

# Bump when the plan-hash representation changes so old stamps compare unequal.
_PLAN_HASH_VERSION = 1


def resolve_wordlist(cfg: ResolvedConfig) -> WordList:
    bundled = load_wordlist()
    user = load_wordlist(cfg.detect.wordlist) if cfg.detect.wordlist else None
    return merge_wordlists(bundled, user)


def compute_fingerprint(*, source_size: int, source_mtime: float, cfg: ResolvedConfig) -> str:
    """R10 base fingerprint: source identity (size+mtime) + resolved settings
    + app version -- deliberately *excluding* the wordlist, whose effect on a
    given file is captured separately by the plan hash (Option 4 two-tier skip).

    `source_path` is excluded so host-vs-container path views agree; `service`
    and `preset_names` are excluded (they can't affect output content); and
    `detect.wordlist` (the wordlist path) is excluded too -- all wordlist
    identity flows through the wordlist hash / plan hash, not the base.
    """
    payload = {
        "source_size": source_size,
        "source_mtime": source_mtime,
        "settings": cfg.model_dump(
            mode="json",
            exclude={"service": True, "preset_names": True, "detect": {"wordlist"}},
        ),
        "app_version": __version__,
    }
    data = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()


def fingerprint_for_source(source: Path, *, cfg: ResolvedConfig) -> str:
    stat = source.stat()
    return compute_fingerprint(source_size=stat.st_size, source_mtime=stat.st_mtime, cfg=cfg)


def compute_plan_hash(
    *,
    mode: str,
    outcome: str | None,
    windows: list[tuple[float, float]],
    masked_entries: list[tuple[float, float, str]],
    captions_entries: list[tuple[float, float, str]],
) -> str:
    """Hash of the censor *outcome* for one file: the audio mute windows plus
    the masked subtitle/caption content. Two wordlists that produce the same
    plan for a file yield the same hash, so a wordlist edit only forces a
    re-encode of files whose plan actually changes."""
    payload = {
        "v": _PLAN_HASH_VERSION,
        "mode": mode,
        "outcome": outcome,
        "windows": sorted([round(s, 3), round(e, 3)] for s, e in windows),
        "masked": [[round(s, 3), round(e, 3), t] for s, e, t in masked_entries],
        "captions": [[round(s, 3), round(e, 3), t] for s, e, t in captions_entries],
    }
    data = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()


def plan_hash_from_context(ctx: "PipelineContext") -> str:
    """Compute the plan hash from a planned pipeline context."""

    def entries(doc: object) -> list[tuple[float, float, str]]:
        if doc is None:
            return []
        return [(e.start_s, e.end_s, e.text) for e in doc.entries]  # type: ignore[attr-defined]

    return compute_plan_hash(
        mode=ctx.mode,
        outcome=ctx.outcome,
        windows=[(w.start_s, w.end_s) for w in ctx.windows],
        masked_entries=entries(ctx.masked_doc),
        captions_entries=entries(ctx.captions_doc),
    )


def plan_hash_for_source(source: Path, *, cfg: ResolvedConfig) -> str:
    """Run the (cheap) planning stages for `source` and return its plan hash.
    Used by the tier-2 skip check to decide whether a wordlist change actually
    alters this file's censor plan before paying for a re-encode."""
    # Local imports: the runner/stages import this module, so importing them at
    # module scope would be circular.
    from uuid import uuid4

    from censorr.pipeline import runner
    from censorr.pipeline.context import PipelineContext
    from censorr.pipeline.job import Job
    from censorr.pipeline.runner import run_pipeline

    job = Job(id=str(uuid4()), source=source, submitted_by="skip-check")
    ctx = PipelineContext(job=job, cfg=cfg)
    with tempfile.TemporaryDirectory(prefix="censorr-plan-") as workdir:
        ctx = run_pipeline(ctx, Path(workdir), stage_sequence=runner.PLANNING_STAGES)
    return plan_hash_from_context(ctx)


def check_skip(
    source: Path, media_type: MediaType, *, cfg: ResolvedConfig, wordlist: WordList
) -> tuple[bool, NamingPlan]:
    """R10 two-tier skip check (Option 4).

    Tier 1 (cheap, no source processing): the output's base fingerprint
    (source+settings+version) must match, and its embedded wordlist hash must
    equal the current one -- then nothing relevant changed, skip.

    Tier 2 (only when the base matches but the wordlist changed): run the
    planning stages and compare plan hashes. Skip the re-encode iff the wordlist
    edit leaves this file's censor plan unchanged.
    """
    naming_plan = plan_names(source, media_type, cfg.naming, language=cfg.subtitles.language)
    if not naming_plan.video_path.is_file():
        return False, naming_plan

    tags = probe(naming_plan.video_path).format_tags
    embedded_base = tags.get("CENSORR_FINGERPRINT")
    if embedded_base is None or embedded_base != fingerprint_for_source(source, cfg=cfg):
        return False, naming_plan  # missing/legacy stamp, or source/settings/version changed

    if tags.get("CENSORR_WORDLIST_HASH") == wordlist.content_hash:
        return True, naming_plan  # tier 1: wordlist unchanged too

    embedded_plan = tags.get("CENSORR_PLAN_HASH")
    if embedded_plan is None:
        return False, naming_plan  # can't compare -> reprocess (re-stamps)

    try:
        current_plan = plan_hash_for_source(source, cfg=cfg)
    except CensorrError:
        return False, naming_plan  # let the real pipeline surface the error
    return current_plan == embedded_plan, naming_plan
