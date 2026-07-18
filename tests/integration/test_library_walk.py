from pathlib import Path

import pytest
from typer.testing import CliRunner

from censorr.cli.main import app
from censorr.config.schema import ResolvedConfig
from censorr.pipeline.library import find_orphaned_outputs, find_reprocess_candidates
from tests.fixtures import build_movie_fixture

pytestmark = pytest.mark.ffmpeg

cli_runner = CliRunner()


def build_tree(tmp_path: Path) -> dict[str, Path]:
    """A library with: an unprocessed source, a processed pair (source +
    published clean-root output), a Plex extra, a sample file, and an
    orphaned clean-root output (Q18: outputs live under <movies-root>-clean).
    """
    root = tmp_path / "library"

    unprocessed = build_movie_fixture(root / "unprocessed", duration=90.0)

    processed_src = build_movie_fixture(root / "processed", duration=90.0)
    cfg_path = tmp_path / "censorr.toml"
    cfg_path.write_text(f'[service]\nqueue_path = "{tmp_path / "queue"}"\n')
    result = cli_runner.invoke(app, ["process", str(processed_src), "--config", str(cfg_path)])
    assert result.exit_code == 0, result.stdout
    processed_out = (
        root / "processed-clean" / "Test Movie (2024)"
        / "Test Movie (2024) {edition-Censorr}.mkv"
    )
    assert processed_out.is_file()

    trailer_dir = root / "unprocessed" / "Test Movie (2024)" / "Trailers"
    trailer_dir.mkdir(parents=True)
    trailer = build_movie_fixture(trailer_dir, duration=15.0)

    sample = unprocessed.with_name("Test Movie (2024)-sample.mkv")
    sample.write_bytes(unprocessed.read_bytes())

    # Orphan: a published output whose source was later deleted.
    orphan_src = build_movie_fixture(root / "orphan", duration=90.0)
    result = cli_runner.invoke(app, ["process", str(orphan_src), "--config", str(cfg_path)])
    assert result.exit_code == 0, result.stdout
    orphan_out = (
        root / "orphan-clean" / "Test Movie (2024)" / "Test Movie (2024) {edition-Censorr}.mkv"
    )
    assert orphan_out.is_file()
    orphan_src.unlink()

    return {
        "root": root,
        "cfg_path": cfg_path,
        "unprocessed": unprocessed,
        "processed_src": processed_src,
        "processed_out": processed_out,
        "trailer": trailer,
        "sample": sample,
        "orphan_out": orphan_out,
    }


def test_reprocess_and_reconcile_touch_exactly_the_right_sets(tmp_path: Path) -> None:
    tree = build_tree(tmp_path)
    cfg = ResolvedConfig(service={"queue_path": str(tmp_path / "queue")})

    # --- find_reprocess_candidates: sources only, no outputs/extras/samples
    candidates = find_reprocess_candidates(tree["root"], cfg)
    assert tree["unprocessed"] in candidates
    assert tree["processed_src"] in candidates  # candidate; fingerprint check filters it later
    assert tree["processed_out"] not in candidates
    assert tree["trailer"] not in candidates
    assert tree["sample"] not in candidates
    assert tree["orphan_out"] not in candidates

    # --- reprocess --dry-run: fingerprint-fresh processed_src drops out too
    result = cli_runner.invoke(
        app,
        ["reprocess", str(tree["root"]), "--config", str(tree["cfg_path"]), "--dry-run"],
    )
    assert result.exit_code == 0
    assert str(tree["unprocessed"]) in result.stdout
    assert str(tree["processed_src"]) not in result.stdout

    # --- reconcile: the orphan-clean root holds exactly one orphan
    orphan_clean_root = tree["root"] / "orphan-clean"
    orphans = find_orphaned_outputs(orphan_clean_root, cfg)
    assert orphans == [tree["orphan_out"]]
    # ...and the processed-clean root holds none (its source still exists).
    assert find_orphaned_outputs(tree["root"] / "processed-clean", cfg) == []

    dry = cli_runner.invoke(
        app,
        ["reconcile", str(orphan_clean_root), "--config", str(tree["cfg_path"]), "--dry-run"],
    )
    assert dry.exit_code == 0
    assert str(tree["orphan_out"]) in dry.stdout
    assert tree["orphan_out"].is_file()  # dry-run deletes nothing

    real = cli_runner.invoke(
        app, ["reconcile", str(orphan_clean_root), "--config", str(tree["cfg_path"])]
    )
    assert real.exit_code == 0
    assert not tree["orphan_out"].exists()
    assert tree["processed_out"].is_file()  # non-orphan output untouched


def test_reprocess_processes_stale_files_for_real(tmp_path: Path) -> None:
    root = tmp_path / "library"
    source = build_movie_fixture(root, duration=90.0)
    cfg_path = tmp_path / "censorr.toml"
    cfg_path.write_text(f'[service]\nqueue_path = "{tmp_path / "queue"}"\n')

    result = cli_runner.invoke(app, ["reprocess", str(root), "--config", str(cfg_path)])

    assert result.exit_code == 0
    assert "published" in result.stdout
    expected = (
        tmp_path / "library-clean" / "Test Movie (2024)"
        / "Test Movie (2024) {edition-Censorr}.mkv"
    )
    assert expected.is_file()
    assert source.is_file()

    # Second run: everything fingerprint-fresh -> empty worklist.
    rerun = cli_runner.invoke(
        app, ["reprocess", str(root), "--config", str(cfg_path), "--dry-run"]
    )
    assert rerun.exit_code == 0
    assert "0 file(s) would be processed" in rerun.stdout
