"""resolve_audio_codec: R13 codec policy + source-bitrate preservation."""

from censorr.config.schema import AudioConfig
from censorr.media.ffmpeg import resolve_audio_codec


class TestSourceBitratePreserved:
    def test_reuses_source_codec_and_matches_source_bitrate(self) -> None:
        # The Bullet Train case: eac3 5.1 @ 640k must not shrink to the 448k
        # codec default.
        codec, bitrate = resolve_audio_codec("eac3", 6, AudioConfig(), source_bitrate=640000)
        assert codec == "eac3"
        assert bitrate == "640000"

    def test_falls_back_to_codec_default_when_bitrate_unknown(self) -> None:
        codec, bitrate = resolve_audio_codec("eac3", 6, AudioConfig(), source_bitrate=None)
        assert (codec, bitrate) == ("eac3", "448k")

    def test_zero_or_negative_bitrate_falls_back(self) -> None:
        assert resolve_audio_codec("aac", 2, AudioConfig(), source_bitrate=0) == ("aac", "192k")

    def test_preserves_aac_source_bitrate(self) -> None:
        assert resolve_audio_codec("aac", 2, AudioConfig(), source_bitrate=256000) == (
            "aac",
            "256000",
        )

    def test_flac_stays_bitrate_less_regardless_of_source(self) -> None:
        assert resolve_audio_codec("flac", 2, AudioConfig(), source_bitrate=900000) == (
            "flac",
            None,
        )


class TestFallbackAndOverrides:
    def test_eac3_over_six_channels_uses_configured_fallback(self) -> None:
        # eac3 > 5.1 can't round-trip (R13): fallback codec/bitrate win, and the
        # source bitrate is intentionally ignored.
        cfg = AudioConfig()  # fallback_codec=eac3, fallback_bitrate=640k
        assert resolve_audio_codec("eac3", 8, cfg, source_bitrate=1500000) == ("eac3", "640k")

    def test_unencodable_source_uses_configured_fallback(self) -> None:
        cfg = AudioConfig(fallback_codec="aac", fallback_bitrate="256k")
        assert resolve_audio_codec("truehd", 8, cfg, source_bitrate=3000000) == ("aac", "256k")

    def test_target_codec_wins_and_ignores_source_bitrate(self) -> None:
        cfg = AudioConfig(target_codec="aac")
        assert resolve_audio_codec("eac3", 6, cfg, source_bitrate=640000) == ("aac", "192k")

    def test_source_bitrate_optional_defaults_to_codec_default(self) -> None:
        # Back-compat: callers that don't pass source_bitrate still work.
        assert resolve_audio_codec("eac3", 6, AudioConfig()) == ("eac3", "448k")
