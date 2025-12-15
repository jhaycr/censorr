import csv
import json
import os
import re
from typing import Any, List, Sequence

import pysubs2

from censorr.commands.abstract_command import Command
from censorr.utils.filesystem import ensure_output_dir
from censorr.utils.fuzzy import FuzzyTerm, MatchResult, SimpleFuzzyMatcher
from censorr.utils.logging import get_logger


logger = get_logger(__name__)

DEFAULT_THRESHOLD = 85.0


class SubtitleMask(Command):
    """Mask profanities in subtitles and emit a CSV of matches (fuzzy)."""

    def do(
        self,
        input_file_path: str,
        output_dir: str,
        config_path: str,
        *,
        default_threshold: float = DEFAULT_THRESHOLD,
    ):
        output_dir = ensure_output_dir(output_dir)

        terms = self._load_profanity_terms(config_path, default_threshold)
        if not terms:
            raise RuntimeError(f"No profanities configured in {config_path}")

        matcher = SimpleFuzzyMatcher(terms, default_threshold=default_threshold)
        logger.info("Loaded %d profanity terms from %s", len(terms), config_path)

        subtitles = pysubs2.load(input_file_path)
        all_matches: List[dict] = []

        for event in subtitles.events:
            masked_text, event_matches, original_text = self._process_event(
                event, matcher
            )
            event.text = masked_text
            all_matches.extend(
                self._format_match_rows(event, masked_text, original_text, event_matches)
            )

        masked_path = os.path.join(output_dir, "masked_subtitles.srt")
        subtitles.save(masked_path, format="srt")
        logger.info("Masked subtitles saved to %s", masked_path)

        if all_matches:
            csv_path = os.path.join(output_dir, "profanity_matches.csv")
            self._write_matches_csv(csv_path, all_matches)
            logger.info("Match CSV saved to %s (%d rows)", csv_path, len(all_matches))
        else:
            logger.info("No profanity matches found; CSV not written")

    def _process_event(
        self, event: Any, matcher: SimpleFuzzyMatcher
    ) -> tuple[str, Sequence[MatchResult], str]:
        original_text = event.text
        matches = matcher.find_matches(original_text)
        masked_text = self._mask_text(original_text, matches)
        return masked_text, matches, original_text

    def _format_match_rows(
        self, event: Any, masked_text: str, original_text: str, matches: Sequence[MatchResult]
    ) -> List[dict]:
        rows: List[dict] = []
        for match in matches:
            rows.append(
                {
                    "start_ms": event.start,
                    "end_ms": event.end,
                    "matched_text": match.window_text,
                    "target_word": match.term.word,
                    "score": match.score,
                    "original_text": original_text,
                    "masked_text": masked_text,
                }
            )
        return rows

    def _load_profanity_terms(
        self, config_path: str, default_threshold: float
    ) -> List[FuzzyTerm]:
        items = self._load_config_items(config_path)
        terms: List[FuzzyTerm] = []

        for item in items:
            if isinstance(item, str):
                word = item.strip()
                if word:
                    terms.append(FuzzyTerm(word=word, threshold=default_threshold))
            elif isinstance(item, dict):
                word = str(item.get("word") or "").strip()
                if not word:
                    continue
                threshold = item.get("threshold", item.get("fuzzy_threshold", default_threshold))
                strategy = str(item.get("variant_strategy", "")).lower()
                aggressive = bool(item.get("aggressive", False)) or strategy == "aggressive"
                terms.append(
                    FuzzyTerm(
                        word=word,
                        threshold=float(threshold),
                        aggressive=aggressive,
                    )
                )

        return terms

    def _load_config_items(self, config_path: str) -> List[object]:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        try:
            data = json.loads(content)
            if isinstance(data, dict) and "profanities" in data:
                items = data.get("profanities") or []
            else:
                items = data

            if not isinstance(items, list):
                raise ValueError(
                    "Profanity config must be a list or dict with 'profanities'"
                )
            return items
        except json.JSONDecodeError:
            lines = [ln.strip() for ln in content.splitlines()]
            return [ln for ln in lines if ln and not ln.startswith("#")]

    def _mask_text(self, text: str, matches: Sequence[MatchResult]) -> str:
        if not matches:
            return text

        masked = text
        ordered = sorted(matches, key=lambda m: len(m.window_text), reverse=True)

        for match in ordered:
            patterns = [match.window_text, match.term.word]
            for pat in patterns:
                if not pat:
                    continue
                escaped = re.escape(pat)
                regex = rf"\b{escaped}\b"
                new_masked, count = re.subn(
                    regex,
                    lambda m: "*" * len(m.group(0)),
                    masked,
                    flags=re.IGNORECASE,
                )
                masked = new_masked
                if count > 0:
                    break

        return masked

    def _write_matches_csv(self, path: str, rows: List[dict]) -> None:
        fieldnames = [
            "start_ms",
            "end_ms",
            "matched_text",
            "target_word",
            "score",
            "original_text",
            "masked_text",
        ]
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
