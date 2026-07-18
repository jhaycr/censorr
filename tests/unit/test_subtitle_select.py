from censorr.media.probe import MediaInfo, StreamInfo
from censorr.subtitles.select import (
    normalize_language,
    select_audio_track,
    select_subtitle_track,
    select_tracks,
    text_subtitle_streams,
)


def stream(
    index: int,
    codec_type: str,
    codec_name: str,
    *,
    language: str | None = None,
    title: str | None = None,
    disposition: dict[str, bool] | None = None,
) -> StreamInfo:
    return StreamInfo(
        index=index,
        codec_type=codec_type,
        codec_name=codec_name,
        language=language,
        title=title,
        disposition=disposition or {},
    )


def media(streams: list[StreamInfo]) -> MediaInfo:
    # Never touched on disk -- just an identifier for the synthetic MediaInfo.
    return MediaInfo(path="/tmp/fake.mkv", duration_s=100.0, streams=streams)  # noqa: S108


class TestNormalizeLanguage:
    def test_two_letter_maps_to_three_letter(self) -> None:
        assert normalize_language("en") == "eng"

    def test_three_letter_passthrough(self) -> None:
        assert normalize_language("eng") == "eng"

    def test_none_and_empty(self) -> None:
        assert normalize_language(None) == ""
        assert normalize_language("") == ""

    def test_unknown_code_passthrough(self) -> None:
        assert normalize_language("xx") == "xx"


class TestBitmapExclusion:
    def test_bitmap_codecs_excluded_from_text_streams(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "subtitle", "hdmv_pgs_subtitle", language="eng"),
                stream(2, "subtitle", "dvd_subtitle", language="eng"),
                stream(3, "subtitle", "subrip", language="eng"),
            ]
        )

        text_streams = text_subtitle_streams(info)

        assert [s.index for s in text_streams] == [3]

    def test_bitmap_only_selects_nothing(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "audio", "aac", language="eng"),
                stream(2, "subtitle", "hdmv_pgs_subtitle", language="eng"),
            ]
        )

        selected = select_subtitle_track(info, language="en", exclude_titles=[])

        assert selected is None


class TestSdhExclusion:
    def test_sdh_titled_track_excluded(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "subtitle", "subrip", language="eng", title="English"),
                stream(2, "subtitle", "subrip", language="eng", title="English (SDH)"),
            ]
        )

        selected = select_subtitle_track(info, language="en", exclude_titles=["sdh", "hi", "cc"])

        assert selected is not None
        assert selected.index == 1

    def test_hearing_impaired_disposition_excluded_even_without_sdh_title(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "subtitle", "subrip", language="eng", title="English"),
                stream(
                    2,
                    "subtitle",
                    "subrip",
                    language="eng",
                    title="English",
                    disposition={"hearing_impaired": True},
                ),
            ]
        )

        selected = select_subtitle_track(info, language="en", exclude_titles=[])

        assert selected is not None
        assert selected.index == 1

    def test_only_sdh_available_selects_nothing(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "subtitle", "subrip", language="eng", title="English (SDH)"),
            ]
        )

        selected = select_subtitle_track(info, language="en", exclude_titles=["sdh"])

        assert selected is None


class TestForcedExclusion:
    def test_forced_track_excluded_from_primary_selection(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "subtitle", "subrip", language="eng", disposition={"forced": True}),
                stream(2, "subtitle", "subrip", language="eng"),
            ]
        )

        selected = select_subtitle_track(info, language="en", exclude_titles=[])

        assert selected is not None
        assert selected.index == 2


class TestLanguageFilter:
    def test_selects_matching_language(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "subtitle", "subrip", language="spa"),
                stream(2, "subtitle", "subrip", language="eng"),
            ]
        )

        selected = select_subtitle_track(info, language="en", exclude_titles=[])

        assert selected is not None
        assert selected.index == 2

    def test_no_matching_language_selects_nothing(self) -> None:
        info = media([stream(0, "video", "h264"), stream(1, "subtitle", "subrip", language="spa")])

        selected = select_subtitle_track(info, language="en", exclude_titles=[])

        assert selected is None

    def test_prefers_default_disposition_among_matches(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "subtitle", "subrip", language="eng"),
                stream(2, "subtitle", "subrip", language="eng", disposition={"default": True}),
            ]
        )

        selected = select_subtitle_track(info, language="en", exclude_titles=[])

        assert selected is not None
        assert selected.index == 2


class TestAudioSelection:
    def test_exact_language_match_preferred(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "audio", "aac", language="jpn"),
                stream(2, "audio", "aac", language="eng"),
            ]
        )

        audio, mismatch = select_audio_track(info, subtitle_language="eng")

        assert audio.index == 2
        assert mismatch is False

    def test_falls_back_to_untagged(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "audio", "aac", language=None),
            ]
        )

        audio, mismatch = select_audio_track(info, subtitle_language="eng")

        assert audio.index == 1
        assert mismatch is False

    def test_falls_back_to_default_with_mismatch_flagged(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "audio", "aac", language="jpn", disposition={"default": True}),
            ]
        )

        audio, mismatch = select_audio_track(info, subtitle_language="eng")

        assert audio.index == 1
        assert mismatch is True

    def test_no_audio_streams_raises(self) -> None:
        info = media([stream(0, "video", "h264")])

        try:
            select_audio_track(info, subtitle_language="eng")
            raised = False
        except ValueError:
            raised = True
        assert raised


class TestSelectTracks:
    def test_happy_path(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "audio", "aac", language="eng"),
                stream(2, "subtitle", "subrip", language="eng", title="English"),
            ]
        )

        selection = select_tracks(info, language="en", exclude_titles=["sdh", "hi", "cc"])

        assert selection.audio_stream == 1
        assert selection.subtitle_stream == 2
        assert selection.subtitle_lang == "eng"
        assert selection.subtitle_source == "embedded"
        assert selection.language_mismatch is False

    def test_language_mismatch_detected(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "audio", "aac", language="jpn", disposition={"default": True}),
                stream(2, "subtitle", "subrip", language="eng"),
            ]
        )

        selection = select_tracks(info, language="en", exclude_titles=[])

        assert selection.subtitle_stream == 2
        assert selection.audio_stream == 1
        assert selection.language_mismatch is True

    def test_no_subtitle_selects_none_and_source_none(self) -> None:
        info = media(
            [
                stream(0, "video", "h264"),
                stream(1, "audio", "aac", language="eng"),
            ]
        )

        selection = select_tracks(info, language="en", exclude_titles=[])

        assert selection.subtitle_stream is None
        assert selection.subtitle_source == "none"
