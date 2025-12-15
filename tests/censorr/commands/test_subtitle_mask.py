import csv
from pathlib import Path

from censorr.commands.subtitle_mask import SubtitleMask


def make_srt(lines: list[str]) -> str:
    """Create a minimal valid SRT from plain text lines, one per cue."""
    blocks = []
    for i, text in enumerate(lines, start=1):
        start_s = 1 + 2 * (i - 1)
        end_s = start_s + 1
        blocks.append(
            f"{i}\n00:00:{start_s:02d},000 --> 00:00:{end_s:02d},000\n{text}\n"
        )
    return "\n".join(blocks) + "\n"


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_csv_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_masks_and_writes_csv(tmp_path):
    # Input subtitles: one line with profanity, one clean
    srt_content = make_srt(["This is damn funny.", "Nothing to see here."])
    srt_path = tmp_path / "in.srt"
    write_file(srt_path, srt_content)

    # Profanity config as simple JSON list
    cfg_path = tmp_path / "profanities.json"
    write_file(cfg_path, "[\n  \"damn\"\n]")

    out_dir = tmp_path / "out"
    op = SubtitleMask()
    op.do(
        input_file_path=str(srt_path),
        output_dir=str(out_dir),
        config_path=str(cfg_path),
    )

    masked_path = out_dir / "masked_subtitles.srt"
    assert masked_path.exists()
    masked = masked_path.read_text(encoding="utf-8")
    assert "This is **** funny." in masked
    assert "Nothing to see here." in masked

    csv_path = out_dir / "profanity_matches.csv"
    assert csv_path.exists(), "Expected matches CSV to be written"
    rows = read_csv_rows(csv_path)
    # At least one match row for the masked word
    assert any(r["matched_text"].lower() == "damn" and r["target_word"].lower() == "damn" for r in rows)


def test_no_matches_no_csv(tmp_path):
    srt_content = make_srt(["Hello world."])
    srt_path = tmp_path / "in.srt"
    write_file(srt_path, srt_content)

    cfg_path = tmp_path / "profanities.json"
    write_file(cfg_path, "[\n  \"foobar\"\n]")

    out_dir = tmp_path / "out"
    op = SubtitleMask()
    op.do(
        input_file_path=str(srt_path),
        output_dir=str(out_dir),
        config_path=str(cfg_path),
    )

    masked = (out_dir / "masked_subtitles.srt").read_text(encoding="utf-8")
    assert "Hello world." in masked
    assert not (out_dir / "profanity_matches.csv").exists()


def test_config_dict_format_and_case_insensitive(tmp_path):
    srt_content = make_srt(["heck HECK HeCk?", "clean line"])  # mixed case and punctuation
    srt_path = tmp_path / "in.srt"
    write_file(srt_path, srt_content)

    cfg_path = tmp_path / "profanities.json"
    # Use dict format with per-item structure
    write_file(
        cfg_path,
        "{"
        "\n  \"profanities\": [\n    {\n      \"word\": \"Heck\",\n      \"threshold\": 85\n    }\n  ]\n"
        "}\n",
    )

    out_dir = tmp_path / "out"
    op = SubtitleMask()
    op.do(
        input_file_path=str(srt_path),
        output_dir=str(out_dir),
        config_path=str(cfg_path),
    )

    masked = (out_dir / "masked_subtitles.srt").read_text(encoding="utf-8")
    # All variants of heck should be masked case-insensitively
    assert "**** **** ****?" in masked

    rows = read_csv_rows(out_dir / "profanity_matches.csv")
    assert rows, "Expected matches to be recorded"
    assert all(r["target_word"].lower() == "heck" for r in rows)


def test_word_boundary_not_substring(tmp_path):
    srt_content = make_srt(["damnation shouldn't be censored.", "damn should be."])
    srt_path = tmp_path / "in.srt"
    write_file(srt_path, srt_content)

    cfg_path = tmp_path / "profanities.json"
    write_file(cfg_path, "[\n  \"damn\"\n]")

    out_dir = tmp_path / "out"
    op = SubtitleMask()
    op.do(
        input_file_path=str(srt_path),
        output_dir=str(out_dir),
        config_path=str(cfg_path),
    )

    masked = (out_dir / "masked_subtitles.srt").read_text(encoding="utf-8")
    # Substring 'damn' inside 'damnation' should NOT be masked
    assert "damnation shouldn't be censored." in masked
    # Standalone 'damn' should be masked
    assert "**** should be." in masked


def test_multiple_terms_and_overlapping(tmp_path):
    srt_content = make_srt(["damn heck", "the heckin mess"])  # heckin matches via suffix 'in'
    srt_path = tmp_path / "in.srt"
    write_file(srt_path, srt_content)

    cfg_path = tmp_path / "profanities.json"
    write_file(cfg_path, "[\n  \"damn\",\n  {\n    \"word\": \"heck\"\n  }\n]\n")

    out_dir = tmp_path / "out"
    op = SubtitleMask()
    op.do(
        input_file_path=str(srt_path),
        output_dir=str(out_dir),
        config_path=str(cfg_path),
    )

    masked = (out_dir / "masked_subtitles.srt").read_text(encoding="utf-8")
    # First line: both words masked
    assert "**** ****" in masked
    # Second line: 'heckin' fully masked due to allowed suffix matching
    assert "the ****** mess" in masked

    rows = read_csv_rows(out_dir / "profanity_matches.csv")
    matched = {r["target_word"].lower() for r in rows}
    assert {"damn", "heck"}.issubset(matched)


def test_multiple_occurrences_generate_multiple_rows(tmp_path):
    srt_content = make_srt(["damn, damn! damn?"])
    srt_path = tmp_path / "in.srt"
    write_file(srt_path, srt_content)

    cfg_path = tmp_path / "profanities.json"
    write_file(cfg_path, "[\n  \"damn\"\n]")

    out_dir = tmp_path / "out"
    op = SubtitleMask()
    op.do(
        input_file_path=str(srt_path),
        output_dir=str(out_dir),
        config_path=str(cfg_path),
    )

    masked = (out_dir / "masked_subtitles.srt").read_text(encoding="utf-8")
    assert masked.count("****") >= 3
    rows = read_csv_rows(out_dir / "profanity_matches.csv")
    # Expect at least three matches recorded
    assert sum(1 for r in rows if r["target_word"].lower() == "damn") >= 3


def test_aggressive_strategy_matches_compounds(tmp_path):
    srt_content = make_srt(["They often misuse tools."])
    srt_path = tmp_path / "in.srt"
    write_file(srt_path, srt_content)

    cfg_path = tmp_path / "profanities.json"
    # Enable aggressive matching for 'use' to match 'misuse'
    write_file(
        cfg_path,
        "[\n  {\n    \"word\": \"use\",\n    \"variant_strategy\": \"aggressive\"\n  }\n]\n",
    )

    out_dir = tmp_path / "out"
    op = SubtitleMask()
    op.do(
        input_file_path=str(srt_path),
        output_dir=str(out_dir),
        config_path=str(cfg_path),
    )

    masked = (out_dir / "masked_subtitles.srt").read_text(encoding="utf-8")
    assert "They often  tools." not in masked  # ensure not wiping whole line
    assert "mis****" in masked or "******" in masked  # 'misuse' should be masked at least partially
    rows = read_csv_rows(out_dir / "profanity_matches.csv")
    assert any(r["target_word"].lower() == "use" for r in rows)


def test_raises_when_no_profanities_in_config(tmp_path):
    srt_content = make_srt(["clean text"])
    srt_path = tmp_path / "in.srt"
    write_file(srt_path, srt_content)

    cfg_path = tmp_path / "profanities.json"
    write_file(cfg_path, "[]\n")

    out_dir = tmp_path / "out"
    op = SubtitleMask()
    try:
        op.do(
            input_file_path=str(srt_path),
            output_dir=str(out_dir),
            config_path=str(cfg_path),
        )
        assert False, "Expected RuntimeError for empty profanities config"
    except RuntimeError:
        pass


def test_accented_term_matches_original_text(tmp_path):
    # Use accented term in config, original text with accent should be masked
    srt_content = make_srt(["café is nice"])  # original includes accent
    srt_path = tmp_path / "in.srt"
    write_file(srt_path, srt_content)

    cfg_path = tmp_path / "profanities.json"
    write_file(cfg_path, "[\n  \"café\"\n]\n")

    out_dir = tmp_path / "out"
    op = SubtitleMask()
    op.do(
        input_file_path=str(srt_path),
        output_dir=str(out_dir),
        config_path=str(cfg_path),
    )

    masked = (out_dir / "masked_subtitles.srt").read_text(encoding="utf-8")
    assert "**** is nice" in masked
