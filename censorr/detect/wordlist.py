import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

DEFAULT_WORDLIST_PATH = Path(__file__).parent.parent / "wordlists" / "default.json"


class Word(BaseModel):
    model_config = ConfigDict(frozen=True)

    word: str
    threshold: float | None = None
    replacement: str | None = None
    aggressive: bool = False

    def effective_threshold(self, global_default: float) -> float:
        """Length-based minimum (R1): words <=4 chars never drop below 95%."""
        base = self.threshold if self.threshold is not None else global_default
        if len(self.word) <= 4:
            return max(base, 95.0)
        return base


class WordList(BaseModel):
    model_config = ConfigDict(frozen=True)

    words: list[Word] = []
    allowlist: list[str] = []

    @property
    def content_hash(self) -> str:
        payload = json.dumps(
            {
                "words": [w.model_dump() for w in self.words],
                "allowlist": sorted(self.allowlist),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def load_wordlist(path: Path | None = None) -> WordList:
    """Load the bundled default wordlist, or a user-supplied one at `path`."""
    target = path or DEFAULT_WORDLIST_PATH
    data = json.loads(target.read_text())
    return WordList.model_validate(data)


def merge_wordlists(bundled: WordList, user: WordList | None) -> WordList:
    """Overlay a user wordlist onto the bundled one.

    User entries for an existing word override the bundled entry's config;
    new words are added. The user allowlist extends (never replaces) the
    bundled allowlist.
    """
    if user is None:
        return bundled
    merged_words: dict[str, Word] = {w.word.lower(): w for w in bundled.words}
    for w in user.words:
        merged_words[w.word.lower()] = w
    merged_allowlist = sorted(set(bundled.allowlist) | set(user.allowlist))
    return WordList(words=list(merged_words.values()), allowlist=merged_allowlist)
