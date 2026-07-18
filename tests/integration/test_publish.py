import json
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from censorr.cli.main import app
from censorr.config.schema import ResolvedConfig
from censorr.pipeline.context import PipelineContext
from censorr.pipeline.errors import QCError
from censorr.pipeline.job import Job
from censorr.pipeline.runner import run_pipeline
from tests.fixtures import (
    CLEAN_ENTRIES,
    build_episode_fixture,
    build_language_mismatch_fixture,
    build_movie_fixture,
    build_no_subtitle_fixture,
)

pytestmark = pytest.mark.ffmpeg

cli_runner = CliRunner()


def cfg_with_queue(tmp_path: Path, **overrides: object) -> ResolvedConfig:
    overrides.setdefault("service", {})
    overrides["service"] = {**overrides["service"], "queue_path": str(tmp_path / "queue")}  # type: ignore[dict-item]
    return ResolvedConfig(**overrides)  # type: ignore[arg-type]


def run_full(
    source: Path, tmp_path: Path, cfg: ResolvedConfig | None = None, **job_kwargs: object
) -> PipelineContext:
    job = Job(id=str(uuid4()), source=source, submitted_by="cli", **job_kwargs)  # type: ignore[arg-type]
    ctx = PipelineContext(job=job, cfg=cfg or cfg_with_queue(tmp_path))
    return run_pipeline(ctx, tmp_path / "workdir")


class TestFullPublish:
    def test_publishes_to_golden_movie_path(self, tmp_path: Path) -> None:
        source = build_movie_fixture(tmp_path / "src", duration=90.0)

        ctx = run_full(source, tmp_path)

        assert ctx.outcome is None
        assert ctx.naming_plan is not None
        assert ctx.naming_plan.video_path == source.with_name(
            "Test Movie (2024) {edition-Censorr}.mkv"
        )
        assert ctx.naming_plan.video_path.is_file()
        assert source.is_file()  # original untouched

    def test_episode_lands_in_derived_clean_root(self, tmp_path: Path) -> None:
        tv_root = tmp_path / "tv"
        source = build_episode_fixture(tv_root, duration=90.0)

        ctx = run_full(source, tmp_path)

        assert ctx.naming_plan is not None
        expected = tmp_path / "tv-clean" / "Test Show" / "Season 01" / source.name
        assert ctx.naming_plan.video_path == expected
        assert expected.is_file()


class TestFingerprintSkip:
    def test_rerun_skips_without_force(self, tmp_path: Path) -> None:
        source = build_movie_fixture(tmp_path / "src", duration=90.0)
        cfg_path = tmp_path / "censorr.toml"
        cfg_path.write_text(f'[service]\nqueue_path = "{tmp_path / "queue"}"\n')

        first = cli_runner.invoke(app, ["process", str(source), "--config", str(cfg_path)])
        assert first.exit_code == 0

        second = cli_runner.invoke(app, ["process", str(source), "--config", str(cfg_path)])
        assert second.exit_code == 2
        assert "fingerprint_match" in second.stdout

    def test_force_bypasses_skip_and_reruns(self, tmp_path: Path) -> None:
        source = build_movie_fixture(tmp_path / "src", duration=90.0)
        cfg_path = tmp_path / "censorr.toml"
        cfg_path.write_text(f'[service]\nqueue_path = "{tmp_path / "queue"}"\n')

        first = cli_runner.invoke(app, ["process", str(source), "--config", str(cfg_path)])
        assert first.exit_code == 0

        forced = cli_runner.invoke(
            app, ["process", str(source), "--config", str(cfg_path), "--force"]
        )
        assert forced.exit_code == 0
        assert "Published:" in forced.stdout

    def test_modified_wordlist_reprocesses_and_replaces(self, tmp_path: Path) -> None:
        source = build_movie_fixture(tmp_path / "src", duration=90.0)

        first_cfg = cfg_with_queue(tmp_path)
        first_ctx = run_full(source, tmp_path, cfg=first_cfg)
        assert first_ctx.outcome is None
        first_mtime = first_ctx.naming_plan.video_path.stat().st_mtime  # type: ignore[union-attr]

        wordlist_path = tmp_path / "custom.json"
        wordlist_path.write_text(json.dumps({"words": [{"word": "fuck"}], "allowlist": []}))
        second_cfg = cfg_with_queue(tmp_path, detect={"wordlist": str(wordlist_path)})

        second_ctx = run_full(source, tmp_path, cfg=second_cfg)

        assert second_ctx.outcome is None
        assert second_ctx.naming_plan.video_path == first_ctx.naming_plan.video_path  # type: ignore[union-attr]
        assert second_ctx.naming_plan.video_path.stat().st_mtime >= first_mtime  # type: ignore[union-attr]


class TestDeletedFilesUpgrade:
    def test_upgrade_removes_superseded_output(self, tmp_path: Path) -> None:
        old_source = build_movie_fixture(tmp_path / "old", duration=90.0)
        old_ctx = run_full(old_source, tmp_path)
        old_output = old_ctx.naming_plan.video_path  # type: ignore[union-attr]
        assert old_output.is_file()

        new_source = build_movie_fixture(tmp_path / "new", duration=90.0)
        new_ctx = run_full(new_source, tmp_path, deleted_files=[old_source])

        assert new_ctx.naming_plan is not None
        assert new_ctx.naming_plan.video_path.is_file()
        assert not old_output.is_file()  # superseded output removed


class TestR16Outcomes:
    def test_zero_match_movie_skips_by_default(self, tmp_path: Path) -> None:
        source = build_movie_fixture(tmp_path / "src", duration=90.0, entries=CLEAN_ENTRIES)

        ctx = run_full(source, tmp_path)

        assert ctx.outcome == "skipped_clean"

    def test_zero_match_episode_publishes_stream_copy(self, tmp_path: Path) -> None:
        source = build_episode_fixture(tmp_path / "tv", duration=90.0, entries=CLEAN_ENTRIES)

        ctx = run_full(source, tmp_path)

        # on_clean_tv defaults to "publish" -- the clean library stays complete.
        assert ctx.mode == "clean"
        assert ctx.outcome is None
        assert ctx.naming_plan is not None
        assert ctx.naming_plan.video_path.is_file()

    def test_no_subtitles_skips(self, tmp_path: Path) -> None:
        source = build_no_subtitle_fixture(tmp_path / "src", duration=30.0)

        ctx = run_full(source, tmp_path)

        assert ctx.outcome == "no_text_subtitles"

    def test_subtitles_only_publishes(self, tmp_path: Path) -> None:
        source = build_language_mismatch_fixture(tmp_path / "src", duration=90.0)

        ctx = run_full(source, tmp_path)

        assert ctx.mode == "subtitles_only"
        assert ctx.outcome is None
        assert ctx.naming_plan is not None
        assert ctx.naming_plan.video_path.is_file()


class TestSidecar:
    def test_no_sidecar_by_default(self, tmp_path: Path) -> None:
        source = build_movie_fixture(tmp_path / "src", duration=90.0)

        ctx = run_full(source, tmp_path)

        assert ctx.naming_plan is not None
        assert ctx.naming_plan.sidecar_paths == []
        # No sidecar next to the published output. (The fixture's own input
        # dialogue.srt lives in the same dir, so match the sidecar stem.)
        assert not list(source.parent.glob("*{edition-Censorr}*.srt"))

    def test_sidecar_written_when_opted_in(self, tmp_path: Path) -> None:
        source = build_movie_fixture(tmp_path / "src", duration=90.0)
        cfg = cfg_with_queue(tmp_path, naming={"write_sidecar": True, "sidecar_token": "censorr"})

        ctx = run_full(source, tmp_path, cfg=cfg)

        assert ctx.naming_plan is not None
        assert len(ctx.naming_plan.sidecar_paths) == 1
        assert ctx.naming_plan.sidecar_paths[0].is_file()


class TestFailedQcLeavesLibraryUntouched:
    def test_qc_failure_does_not_publish(self, tmp_path: Path) -> None:
        source = build_movie_fixture(tmp_path / "src", duration=90.0)
        wordlist_path = tmp_path / "hostile.json"
        hostile = {"words": [{"word": "this", "threshold": 50}], "allowlist": []}
        wordlist_path.write_text(json.dumps(hostile))
        cfg = cfg_with_queue(tmp_path, detect={"wordlist": str(wordlist_path)})

        expected_output = source.with_name("Test Movie (2024) {edition-Censorr}.mkv")

        with pytest.raises(QCError):
            run_full(source, tmp_path, cfg=cfg)

        assert not expected_output.is_file()
