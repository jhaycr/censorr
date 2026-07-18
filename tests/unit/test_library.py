from pathlib import Path

from censorr.config.schema import ResolvedConfig
from censorr.pipeline.library import _strip_censorr_from_edition, derive_source_for_output


class TestStripCensorrFromEdition:
    def test_plain_censorr_tag_removed(self) -> None:
        result = _strip_censorr_from_edition(
            "Test Movie (2024) {edition-Censorr}.mkv", "Censorr"
        )

        assert result == "Test Movie (2024).mkv"

    def test_combined_tag_keeps_other_edition(self) -> None:
        result = _strip_censorr_from_edition(
            "Test Movie (2024) {edition-Director's Cut Censorr}.mkv", "Censorr"
        )

        assert result == "Test Movie (2024) {edition-Director's Cut}.mkv"

    def test_non_censorr_edition_returns_none(self) -> None:
        result = _strip_censorr_from_edition(
            "Test Movie (2024) {edition-Director's Cut}.mkv", "Censorr"
        )

        assert result is None

    def test_no_edition_tag_returns_none(self) -> None:
        assert _strip_censorr_from_edition("Test Movie (2024).mkv", "Censorr") is None

    def test_quality_tokens_survive(self) -> None:
        result = _strip_censorr_from_edition(
            "Test Movie (2024) {edition-Censorr} 1080p.mkv", "Censorr"
        )

        assert result == "Test Movie (2024) 1080p.mkv"


class TestDeriveSourceForOutput:
    def test_movie_output_maps_to_sibling_source(self) -> None:
        cfg = ResolvedConfig()
        output = Path("/movies/Test Movie (2024)/Test Movie (2024) {edition-Censorr}.mkv")

        source = derive_source_for_output(output, Path("/movies"), cfg)

        assert source == Path("/movies/Test Movie (2024)/Test Movie (2024).mkv")

    def test_episode_output_maps_through_clean_suffix(self) -> None:
        cfg = ResolvedConfig()
        clean_root = Path("/data/media/tv-clean")
        output = clean_root / "Show" / "Season 01" / "Show - s01e01.mkv"

        source = derive_source_for_output(output, clean_root, cfg)

        assert source == Path("/data/media/tv/Show/Season 01/Show - s01e01.mkv")

    def test_underivable_mapping_returns_none(self) -> None:
        cfg = ResolvedConfig()
        # No edition tag and the clean root has no -clean suffix.
        clean_root = Path("/data/media/familysafe")
        output = clean_root / "Show" / "Season 01" / "Show - s01e01.mkv"

        assert derive_source_for_output(output, clean_root, cfg) is None
