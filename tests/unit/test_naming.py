from pathlib import Path

import pytest

from censorr.config.schema import NamingConfig
from censorr.naming.models import JobValidationError, MediaType, MediaTypeHint
from censorr.naming.plex import classify, derive_tv_clean_root, plan_names


class TestClassify:
    def test_hint_wins_over_filename(self) -> None:
        # Filename looks like an episode, but the Arr hint says movie.
        assert classify(Path("Show - s01e01.mkv"), MediaTypeHint.MOVIE) == MediaType.MOVIE

    @pytest.mark.parametrize(
        "filename",
        [
            "Show - S01E02.mkv",
            "Show - s1e2.mkv",
            "Show Season 1 Episode 2.mkv",
            "Show 1x02.mkv",
        ],
    )
    def test_filename_patterns_detected_as_episode(self, filename: str) -> None:
        assert classify(Path(filename), None) == MediaType.EPISODE

    def test_plain_movie_filename_defaults_to_movie(self) -> None:
        assert classify(Path("Test Movie (2024).mkv"), None) == MediaType.MOVIE


class TestMovieNaming:
    """Golden table: movie x edition present (combine) / no year / invariant."""

    def test_year_present_no_existing_edition(self) -> None:
        cfg = NamingConfig()
        plan = plan_names(Path("/movies/Test Movie (2024).mkv"), MediaType.MOVIE, cfg)

        assert plan.video_path == Path("/movies/Test Movie (2024) {edition-Censorr}.mkv")
        assert plan.edition_tag_applied == "Censorr"

    def test_edition_tag_inserted_before_quality_tokens(self) -> None:
        cfg = NamingConfig()
        plan = plan_names(Path("/movies/Test Movie (2024) 1080p.mkv"), MediaType.MOVIE, cfg)

        assert plan.video_path == Path("/movies/Test Movie (2024) {edition-Censorr} 1080p.mkv")

    def test_no_year_appends_tag_before_extension(self) -> None:
        cfg = NamingConfig()
        plan = plan_names(Path("/movies/Test Movie.mkv"), MediaType.MOVIE, cfg)

        assert plan.video_path == Path("/movies/Test Movie {edition-Censorr}.mkv")

    def test_existing_edition_tag_combines(self) -> None:
        cfg = NamingConfig()
        source = Path("/movies/Test Movie (2024) {edition-Director's Cut}.mkv")
        plan = plan_names(source, MediaType.MOVIE, cfg)

        assert plan.video_path == Path(
            "/movies/Test Movie (2024) {edition-Director's Cut Censorr}.mkv"
        )
        assert plan.edition_tag_applied == "Director's Cut Censorr"

    def test_custom_edition_tag_from_config(self) -> None:
        cfg = NamingConfig(edition_tag="Clean")
        plan = plan_names(Path("/movies/Test Movie (2024).mkv"), MediaType.MOVIE, cfg)

        assert plan.video_path == Path("/movies/Test Movie (2024) {edition-Clean}.mkv")

    def test_output_never_equals_source(self) -> None:
        cfg = NamingConfig()
        source = Path("/movies/Test Movie (2024).mkv")
        plan = plan_names(source, MediaType.MOVIE, cfg)

        assert plan.video_path != source

    def test_no_sidecar_by_default(self) -> None:
        cfg = NamingConfig()
        plan = plan_names(Path("/movies/Test Movie (2024).mkv"), MediaType.MOVIE, cfg)

        assert plan.sidecar_paths == []

    def test_sidecar_with_custom_token(self) -> None:
        cfg = NamingConfig(write_sidecar=True, sidecar_token="censorr")  # noqa: S106
        source = Path("/movies/Test Movie (2024).mkv")
        plan = plan_names(source, MediaType.MOVIE, cfg, language="en")

        assert plan.sidecar_paths == [
            Path("/movies/Test Movie (2024) {edition-Censorr}.en.censorr.srt")
        ]

    def test_sidecar_pure_plex_spec_when_token_empty(self) -> None:
        cfg = NamingConfig(write_sidecar=True, sidecar_token="")
        source = Path("/movies/Test Movie (2024).mkv")
        plan = plan_names(source, MediaType.MOVIE, cfg, language="en")

        assert plan.sidecar_paths == [Path("/movies/Test Movie (2024) {edition-Censorr}.en.srt")]

    def test_track_titles_set(self) -> None:
        cfg = NamingConfig()
        plan = plan_names(Path("/movies/Test Movie (2024).mkv"), MediaType.MOVIE, cfg)

        assert plan.track_titles == {
            "audio": "English (Censored)",
            "subtitle": "English (Censored)",
        }


class TestTvCleanRootDerivation:
    def test_season_dir_derivation(self) -> None:
        source = Path("/data/media/tv/Show/Season 01/Show - s01e01.mkv")

        assert derive_tv_clean_root(source) == Path("/data/media/tv-clean")

    def test_specials_dir_derivation(self) -> None:
        source = Path("/data/media/tv/Show/Specials/Show - s00e01.mkv")

        assert derive_tv_clean_root(source) == Path("/data/media/tv-clean")

    def test_case_insensitive_season_match(self) -> None:
        source = Path("/data/media/tv/Show/SEASON 02/Show - s02e01.mkv")

        assert derive_tv_clean_root(source) == Path("/data/media/tv-clean")

    def test_no_season_dir_uses_shows_parent_as_root(self) -> None:
        source = Path("/data/media/tv/Show/Show - s01e01.mkv")

        assert derive_tv_clean_root(source) == Path("/data/media/tv-clean")

    def test_shallow_path_refused(self) -> None:
        with pytest.raises(JobValidationError):
            derive_tv_clean_root(Path("/ep.mkv"))


class TestEpisodeNaming:
    def test_season_dir_mirrored_under_derived_clean_root(self) -> None:
        cfg = NamingConfig()
        source = Path("/data/media/tv/Show/Season 01/Show - s01e01.mkv")
        plan = plan_names(source, MediaType.EPISODE, cfg)

        assert plan.video_path == Path(
            "/data/media/tv-clean/Show/Season 01/Show - s01e01.mkv"
        )
        assert plan.edition_tag_applied is None

    def test_specials_dir_mirrored(self) -> None:
        cfg = NamingConfig()
        source = Path("/data/media/tv/Show/Specials/Show - s00e01.mkv")
        plan = plan_names(source, MediaType.EPISODE, cfg)

        assert plan.video_path == Path("/data/media/tv-clean/Show/Specials/Show - s00e01.mkv")

    def test_season_less_mirrors_show_dir_only(self) -> None:
        cfg = NamingConfig()
        source = Path("/data/media/tv/Show/Show - s01e01.mkv")
        plan = plan_names(source, MediaType.EPISODE, cfg)

        assert plan.video_path == Path("/data/media/tv-clean/Show/Show - s01e01.mkv")

    def test_filename_unchanged(self) -> None:
        cfg = NamingConfig()
        source = Path("/data/media/tv/Show/Season 01/Show - s01e01.mkv")
        plan = plan_names(source, MediaType.EPISODE, cfg)

        assert plan.video_path.name == source.name

    def test_explicit_tv_clean_root_overrides_derivation(self) -> None:
        cfg = NamingConfig(tv_clean_root=Path("/mnt/family-safe-tv"))
        source = Path("/data/media/tv/Show/Season 01/Show - s01e01.mkv")
        plan = plan_names(source, MediaType.EPISODE, cfg)

        assert plan.video_path == Path("/mnt/family-safe-tv/Show/Season 01/Show - s01e01.mkv")

    def test_shallow_source_raises_without_explicit_root(self) -> None:
        cfg = NamingConfig()

        with pytest.raises(JobValidationError):
            plan_names(Path("/ep.mkv"), MediaType.EPISODE, cfg)

    def test_misconfigured_clean_root_colliding_with_source_raises(self) -> None:
        # tv_clean_root explicitly pointed at the source's own tree ->
        # the mirrored output path collides with the source itself.
        cfg = NamingConfig(tv_clean_root=Path("/data/media/tv-clean"))
        source = Path("/data/media/tv-clean/Show/Season 01/Show - s01e01.mkv")

        with pytest.raises(JobValidationError):
            plan_names(source, MediaType.EPISODE, cfg)

    def test_no_sidecar_by_default(self) -> None:
        cfg = NamingConfig()
        source = Path("/data/media/tv/Show/Season 01/Show - s01e01.mkv")
        plan = plan_names(source, MediaType.EPISODE, cfg)

        assert plan.sidecar_paths == []

    def test_sidecar_beside_episode_when_enabled(self) -> None:
        cfg = NamingConfig(write_sidecar=True, sidecar_token="censorr")  # noqa: S106
        source = Path("/data/media/tv/Show/Season 01/Show - s01e01.mkv")
        plan = plan_names(source, MediaType.EPISODE, cfg, language="en")

        assert plan.sidecar_paths == [
            Path("/data/media/tv-clean/Show/Season 01/Show - s01e01.en.censorr.srt")
        ]
