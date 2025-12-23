import json
from pathlib import Path
import pytest

from censorr.commands.subtitle_qc import SubtitleQC


def test_subtitle_qc_passes_when_no_terms_found(tmp_path):
    masked = tmp_path / "masked.srt"
    masked.write_text("Hello world", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps(["badword"]), encoding="utf-8")

    qc = SubtitleQC()
    qc.do(input_file_path=str(masked), config_path=str(config))


def test_subtitle_qc_raises_on_hits(tmp_path):
    masked = tmp_path / "masked.srt"
    masked.write_text("This has badword twice: badword", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps(["badword", "other"]), encoding="utf-8")

    qc = SubtitleQC()
    with pytest.raises(RuntimeError):
        qc.do(input_file_path=str(masked), config_path=str(config))


def test_subtitle_qc_supports_profanities_key(tmp_path):
    masked = tmp_path / "masked.srt"
    masked.write_text("clean text", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"profanities": ["bad"]}), encoding="utf-8")

    qc = SubtitleQC()
    qc.do(input_file_path=str(masked), config_path=str(config))
