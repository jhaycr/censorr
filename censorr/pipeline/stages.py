from pathlib import Path

from censorr.audio.windows import AudioSettings, EntrySpanProvider
from censorr.detect.matcher import Matcher
from censorr.detect.wordlist import load_wordlist, merge_wordlists
from censorr.media.ffmpeg import extract_subtitle_stream
from censorr.media.probe import probe as probe_media
from censorr.naming.plex import classify, plan_names
from censorr.pipeline.context import PipelineContext
from censorr.subtitles.io import load as load_subtitle_doc
from censorr.subtitles.mask import mask_entries
from censorr.subtitles.select import select_tracks


def probe(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    media_info = probe_media(ctx.job.source)
    return ctx.model_copy(update={"media_info": media_info})


def select_tracks_stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    assert ctx.media_info is not None, "select_tracks requires media_info from probe"
    selection = select_tracks(
        ctx.media_info,
        language=ctx.cfg.subtitles.language,
        exclude_titles=ctx.cfg.subtitles.exclude_titles,
    )
    if not selection.language_mismatch:
        return ctx.model_copy(update={"selection": selection})
    if ctx.cfg.subtitles.allow_language_mismatch:
        return ctx.model_copy(update={"selection": selection, "mode": "subtitles_only"})
    return ctx.model_copy(update={"selection": selection, "outcome": "language_mismatch"})


def _find_sidecar(source: Path, language: str) -> Path | None:
    for candidate in (source.with_suffix(f".{language}.srt"), source.with_suffix(".srt")):
        if candidate.is_file():
            return candidate
    return None


def acquire_subtitles(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None:
        return ctx
    assert ctx.selection is not None, "acquire_subtitles requires a selection"

    if ctx.selection.subtitle_stream is not None:
        extracted = extract_subtitle_stream(ctx.job.source, ctx.selection.subtitle_stream, workdir)
        doc = load_subtitle_doc(extracted)
        return ctx.model_copy(update={"subtitle_doc": doc})

    sidecar = _find_sidecar(ctx.job.source, ctx.selection.subtitle_lang)
    if sidecar is not None:
        return ctx.model_copy(update={"subtitle_doc": load_subtitle_doc(sidecar)})

    return ctx.model_copy(update={"outcome": "no_text_subtitles"})


def detect(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None:
        return ctx
    assert ctx.subtitle_doc is not None, "detect requires a subtitle_doc from acquire_subtitles"

    bundled = load_wordlist()
    user = load_wordlist(ctx.cfg.detect.wordlist) if ctx.cfg.detect.wordlist else None
    wordlist = merge_wordlists(bundled, user)
    matcher = Matcher(wordlist, similarity_threshold=ctx.cfg.detect.fuzzy_threshold)

    matches = {
        entry.index: found
        for entry in ctx.subtitle_doc.entries
        if (found := matcher.find_matches(entry.plaintext))
    }

    mode = "clean" if not matches and ctx.mode == "full" else ctx.mode
    return ctx.model_copy(update={"matches": matches, "mode": mode})


def plan_windows(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None or ctx.mode in ("clean", "subtitles_only"):
        return ctx
    assert ctx.subtitle_doc is not None, "plan_windows requires a subtitle_doc"

    settings = AudioSettings(buffer_s=ctx.cfg.detect.buffer_s)
    windows = EntrySpanProvider().windows(
        ctx.subtitle_doc.entries, ctx.matches, ctx.job.source, settings
    )
    return ctx.model_copy(update={"windows": windows})


def mask_subtitles_stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None or ctx.subtitle_doc is None:
        return ctx
    masked_doc, captions_doc = mask_entries(ctx.subtitle_doc, ctx.matches)
    return ctx.model_copy(update={"masked_doc": masked_doc, "captions_doc": captions_doc})


def plan_names_stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None:
        return ctx
    media_type = classify(ctx.job.source, ctx.job.media_type_hint)
    naming_plan = plan_names(
        ctx.job.source, media_type, ctx.cfg.naming, language=ctx.cfg.subtitles.language
    )
    return ctx.model_copy(update={"naming_plan": naming_plan})
