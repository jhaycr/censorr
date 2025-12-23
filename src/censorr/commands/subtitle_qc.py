import json
import re
from pathlib import Path
from typing import List

from censorr.commands.abstract_command import Command
from censorr.utils.logging import get_logger

logger = get_logger(__name__)


def _load_profanity_terms(config_path: str) -> List[str]:
    path = Path(config_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "profanities" in data:
        items = data.get("profanities") or []
    else:
        items = data
    terms: List[str] = []
    for item in items:
        if isinstance(item, str):
            word = item.strip()
            if word:
                terms.append(word)
        elif isinstance(item, dict):
            word = str(item.get("word") or "").strip()
            if word:
                terms.append(word)
    return terms


class SubtitleQC(Command):
    """Simple QC to ensure masked subtitles contain no configured profanities."""

    def do(self, input_file_path: str, config_path: str) -> None:
        terms = _load_profanity_terms(config_path)
        if not terms:
            raise RuntimeError(f"No profanities configured in {config_path}")

        text = Path(input_file_path).read_text(encoding="utf-8")
        total_hits = 0
        for term in terms:
            pattern = rf"\b{re.escape(term)}\b"
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            count = len(matches)
            total_hits += count

        if total_hits > 0:
            raise RuntimeError(
                f"Subtitle QC failed: found {total_hits} profanity occurrences in masked subtitles"
            )

        logger.info("Subtitle QC passed: no profanities found")
