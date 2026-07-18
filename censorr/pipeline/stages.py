from pathlib import Path
from typing import Literal

from censorr.audio.windows import AudioSettings, EntrySpanProvider
from censorr.config.schema import ResolvedConfig
from censorr.detect.matcher import Matcher
from censorr.detect.wordlist import WordList, load_wordlist, merge_wordlists
from censorr.media.ffmpeg import RemuxPlan, extract_subtitle_stream, resolve_audio_codec
from censorr.media.ffmpeg import remux as ffmpeg_remux
from censorr.media.probe import probe as probe_media
from censorr.naming.plex import classify, plan_names
from censorr.pipeline.context import PipelineContext
from censorr.pipeline.fingerprint import fingerprint_for_source
from censorr.subtitles.io import load as load_subtitle_doc
from censorr.subtitles.io import save as save_subtitle_doc
from censorr.subtitles.mask import mask_entries
from censorr.subtitles.select import select_tracks


def _resolve_wordlist(cfg: ResolvedConfig) -> WordList:
    bundled = load_wordlist()
    user = load_wordlist(cfg.detect.wordlist) if cfg.detect.wordlist else None
    return merge_wordlists(bundled, user)


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

    wordlist = _resolve_wordlist(ctx.cfg)
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
    if ctx.mode == "subtitles_only":
        # R16: muting windows derived from a translation against foreign
        # speech would be nonsense -- never show a mute caption here.
        captions_doc = None
    return ctx.model_copy(update={"masked_doc": masked_doc, "captions_doc": captions_doc})


def plan_names_stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None:
        return ctx
    media_type = classify(ctx.job.source, ctx.job.media_type_hint)
    naming_plan = plan_names(
        ctx.job.source, media_type, ctx.cfg.naming, language=ctx.cfg.subtitles.language
    )
    return ctx.model_copy(update={"naming_plan": naming_plan})


def remux_stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None:
        return ctx
    assert ctx.media_info is not None, "remux requires media_info from probe"
    assert ctx.selection is not None, "remux requires a selection"
    assert ctx.masked_doc is not None, "remux requires a masked_doc"
    assert ctx.naming_plan is not None, "remux requires a naming_plan"

    masked_sub_path = workdir / "masked.srt"
    save_subtitle_doc(ctx.masked_doc, masked_sub_path)

    captions_sub_path: Path | None = None
    if ctx.captions_doc is not None:
        captions_sub_path = workdir / "captions.srt"
        save_subtitle_doc(ctx.captions_doc, captions_sub_path)

    video_stream = ctx.media_info.video_streams()[0].index
    audio_info = next(
        s for s in ctx.media_info.audio_streams() if s.index == ctx.selection.audio_stream
    )

    audio_mode: Literal["mute_encode", "copy"] = (
        "copy" if ctx.mode in ("clean", "subtitles_only") else "mute_encode"
    )
    audio_codec = audio_bitrate = None
    if audio_mode == "mute_encode":
        audio_codec, audio_bitrate = resolve_audio_codec(
            audio_info.codec_name, audio_info.channels or 2, ctx.cfg.audio
        )

    wordlist = _resolve_wordlist(ctx.cfg)
    fingerprint = fingerprint_for_source(ctx.job.source, cfg=ctx.cfg, wordlist=wordlist)

    plan = RemuxPlan(
        source=ctx.job.source,
        temp_output=workdir / "output.mkv",
        video_stream=video_stream,
        audio_stream=ctx.selection.audio_stream,
        audio_mode=audio_mode,
        audio_codec=audio_codec,
        audio_bitrate=audio_bitrate,
        windows=ctx.windows,
        masked_sub=masked_sub_path,
        captions_sub=captions_sub_path,
        stream_titles=ctx.naming_plan.track_titles,
        language=ctx.selection.subtitle_lang or ctx.cfg.subtitles.language,
        fingerprint=fingerprint,
    )
    temp_output = ffmpeg_remux(plan)
    return ctx.model_copy(update={"temp_output": temp_output})
