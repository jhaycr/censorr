from pathlib import Path

from censorr.config.schema import ResolvedConfig
from censorr.pipeline.library import (
    _strip_censorr_from_edition,
    derive_source_for_output,
    find_backfill_candidates,
    find_reprocess_candidates,
)


def _episode(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not real media")
    return path


class TestFindReprocessCandidates:
    """Only *previously-processed* sources (with a distinct existing output)
    are candidates; nested/aliased clean roots must not self-reprocess."""

    def test_source_with_a_distinct_output_is_a_candidate(self, tmp_path: Path) -> None:
        tv, clean = tmp_path / "tv", tmp_path / "tv-clean"
        src = _episode(tv, "Show/Season 01/Show - s01e01.mkv")
        _episode(clean, "Show/Season 01/Show - s01e01.mkv")  # a distinct output exists
        cfg = ResolvedConfig(naming={"tv_clean_root": str(clean)})

        assert find_reprocess_candidates(tv, cfg) == [src]

    def test_never_processed_source_is_not_a_candidate(self, tmp_path: Path) -> None:
        tv, clean = tmp_path / "tv", tmp_path / "tv-clean"
        _episode(tv, "Show/Season 01/Show - s01e01.mkv")  # no output for it
        clean.mkdir()
        cfg = ResolvedConfig(naming={"tv_clean_root": str(clean)})

        assert find_reprocess_candidates(tv, cfg) == []

    def test_bind_aliased_clean_root_inside_source_is_not_self_reprocessed(
        self, tmp_path: Path
    ) -> None:
        # neo's layout: the clean root is a subdir of the source root, exposed
        # under a second path (bind-mount alias, mimicked here with a symlink).
        # Files living in the clean tree map to themselves -- not sources.
        tv = tmp_path / "tv"
        aliased = _episode(tv, "General_Clean/Show/Season 01/Show - s01e01.mkv")
        clean_alias = tmp_path / "tv-clean"
        clean_alias.symlink_to(tv / "General_Clean")
        cfg = ResolvedConfig(naming={"tv_clean_root": str(clean_alias)})

        assert aliased not in find_reprocess_candidates(tv, cfg)


class TestFindBackfillCandidates:
    """A directory job is explicit first-time bulk censoring: *every* source
    is a candidate, processed or not -- unlike find_reprocess_candidates."""

    def test_never_processed_source_is_a_candidate(self, tmp_path: Path) -> None:
        tv, clean = tmp_path / "tv", tmp_path / "tv-clean"
        src = _episode(tv, "Show/Season 01/Show - s01e01.mkv")
        clean.mkdir()
        cfg = ResolvedConfig(naming={"tv_clean_root": str(clean)})

        assert find_backfill_candidates(tv, cfg) == [src]

    def test_processed_source_is_also_a_candidate(self, tmp_path: Path) -> None:
        tv, clean = tmp_path / "tv", tmp_path / "tv-clean"
        src = _episode(tv, "Show/Season 01/Show - s01e01.mkv")
        _episode(clean, "Show/Season 01/Show - s01e01.mkv")
        cfg = ResolvedConfig(naming={"tv_clean_root": str(clean)})

        assert find_backfill_candidates(tv, cfg) == [src]

    def test_bind_aliased_clean_root_inside_source_is_not_a_candidate(
        self, tmp_path: Path
    ) -> None:
        tv = tmp_path / "tv"
        aliased = _episode(tv, "General_Clean/Show/Season 01/Show - s01e01.mkv")
        clean_alias = tmp_path / "tv-clean"
        clean_alias.symlink_to(tv / "General_Clean")
        cfg = ResolvedConfig(naming={"tv_clean_root": str(clean_alias)})

        assert aliased not in find_backfill_candidates(tv, cfg)


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
    def test_movie_output_maps_through_clean_suffix_and_tag_strip(self) -> None:
        cfg = ResolvedConfig()
        clean_root = Path("/media/movies-clean")
        output = clean_root / "Test Movie (2024)" / "Test Movie (2024) {edition-Censorr}.mkv"

        source = derive_source_for_output(output, clean_root, cfg)

        assert source == Path("/media/movies/Test Movie (2024)/Test Movie (2024).mkv")

    def test_episode_output_maps_through_clean_suffix(self) -> None:
        cfg = ResolvedConfig()
        clean_root = Path("/data/media/tv-clean")
        output = clean_root / "Show" / "Season 01" / "Show - s01e01.mkv"

        source = derive_source_for_output(output, clean_root, cfg)

        assert source == Path("/data/media/tv/Show/Season 01/Show - s01e01.mkv")

    def test_underivable_mapping_returns_none(self) -> None:
        cfg = ResolvedConfig()
        # The clean root has no -clean suffix (explicitly configured
        # elsewhere) -- no reverse mapping, never treated as orphan.
        clean_root = Path("/data/media/familysafe")
        output = clean_root / "Show" / "Season 01" / "Show - s01e01.mkv"

        assert derive_source_for_output(output, clean_root, cfg) is None
