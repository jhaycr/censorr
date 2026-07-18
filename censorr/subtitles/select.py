from pydantic import BaseModel

from censorr.media.probe import MediaInfo, StreamInfo

# R12: only these subtitle codecs carry parseable text; bitmap codecs
# (PGS/hdmv_pgs_subtitle, VOBSUB/dvd_subtitle, dvbsub, xsub) are never
# parsed and never mapped into the clean output.
TEXT_SUBTITLE_CODECS = {"subrip", "ass", "ssa", "webvtt", "mov_text", "text"}

# ISO 639-1 -> ISO 639-2/B, plus a few 639-2/T variants normalized to the
# same canonical form, so config language "en" matches ffprobe's "eng".
_LANGUAGE_ALIASES: dict[str, str] = {
    "en": "eng", "eng": "eng",
    "es": "spa", "spa": "spa",
    "fr": "fre", "fra": "fre", "fre": "fre",
    "de": "ger", "deu": "ger", "ger": "ger",
    "it": "ita", "ita": "ita",
    "pt": "por", "por": "por",
    "ja": "jpn", "jpn": "jpn",
    "zh": "chi", "zho": "chi", "chi": "chi",
    "ko": "kor", "kor": "kor",
    "ru": "rus", "rus": "rus",
    "ar": "ara", "ara": "ara",
    "hi": "hin", "hin": "hin",
}


class TrackSelection(BaseModel):
    audio_stream: int
    audio_lang: str
    subtitle_stream: int | None
    subtitle_lang: str
    subtitle_source: str
    language_mismatch: bool


def normalize_language(code: str | None) -> str:
    if not code:
        return ""
    key = code.strip().lower()
    return _LANGUAGE_ALIASES.get(key, key)


def text_subtitle_streams(media_info: MediaInfo) -> list[StreamInfo]:
    return [s for s in media_info.subtitle_streams() if s.codec_name in TEXT_SUBTITLE_CODECS]


def _is_excluded(stream: StreamInfo, exclude_titles: list[str]) -> bool:
    if stream.disposition.get("hearing_impaired") or stream.disposition.get("forced"):
        return True
    title = (stream.title or "").lower()
    return any(token.lower() in title for token in exclude_titles)


def select_subtitle_track(
    media_info: MediaInfo, *, language: str, exclude_titles: list[str]
) -> StreamInfo | None:
    target = normalize_language(language)
    eligible = [
        s
        for s in text_subtitle_streams(media_info)
        if not _is_excluded(s, exclude_titles) and normalize_language(s.language) == target
    ]
    if not eligible:
        return None
    default = next((s for s in eligible if s.disposition.get("default")), None)
    return default or eligible[0]


def select_audio_track(
    media_info: MediaInfo, *, subtitle_language: str
) -> tuple[StreamInfo, bool]:
    audio_streams = media_info.audio_streams()
    if not audio_streams:
        raise ValueError("media has no audio streams")
    target = normalize_language(subtitle_language)

    exact = next(
        (s for s in audio_streams if target and normalize_language(s.language) == target), None
    )
    if exact is not None:
        return exact, False

    untagged = next(
        (s for s in audio_streams if normalize_language(s.language) in ("", "und")), None
    )
    if untagged is not None:
        return untagged, False

    fallback = next((s for s in audio_streams if s.disposition.get("default")), audio_streams[0])
    return fallback, True


def select_tracks(
    media_info: MediaInfo, *, language: str = "en", exclude_titles: list[str] | None = None
) -> TrackSelection:
    exclude_titles = exclude_titles or []
    subtitle = select_subtitle_track(media_info, language=language, exclude_titles=exclude_titles)
    subtitle_lang = (
        normalize_language(subtitle.language) if subtitle else normalize_language(language)
    )
    audio, mismatch = select_audio_track(media_info, subtitle_language=subtitle_lang)

    return TrackSelection(
        audio_stream=audio.index,
        audio_lang=normalize_language(audio.language),
        subtitle_stream=subtitle.index if subtitle else None,
        subtitle_lang=subtitle_lang,
        subtitle_source="embedded" if subtitle else "none",
        language_mismatch=mismatch,
    )
