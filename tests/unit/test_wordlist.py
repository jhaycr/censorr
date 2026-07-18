from pathlib import Path

from censorr.detect.wordlist import (
    DEFAULT_WORDLIST_PATH,
    Word,
    WordList,
    load_wordlist,
    merge_wordlists,
)


def test_default_wordlist_bundled_and_loadable() -> None:
    wordlist = load_wordlist()

    assert DEFAULT_WORDLIST_PATH.is_file()
    assert len(wordlist.words) > 0
    assert {w.word for w in wordlist.words} >= {"fuck", "shit", "cunt"}


def test_load_wordlist_custom_path(tmp_path: Path) -> None:
    custom = tmp_path / "custom.json"
    custom.write_text('{"words": [{"word": "foo"}], "allowlist": ["food"]}')

    wordlist = load_wordlist(custom)

    assert wordlist.words == [Word(word="foo")]
    assert wordlist.allowlist == ["food"]


def test_word_length_based_threshold_minimum() -> None:
    # Short words (<=4 chars) get a 95% minimum regardless of a lower custom value
    assert Word(word="shit", threshold=80).effective_threshold(85.0) == 95.0
    # Short words with a higher custom threshold keep it
    assert Word(word="fuck", threshold=98).effective_threshold(85.0) == 98.0
    # Long words use their custom threshold as-is
    assert Word(word="bullshit", threshold=70).effective_threshold(85.0) == 70.0
    # Long words with no custom threshold fall back to the global default
    assert Word(word="motherfucker").effective_threshold(85.0) == 85.0


def test_merge_wordlists_overrides_and_unions_allowlist() -> None:
    bundled = WordList(
        words=[Word(word="fuck", threshold=75), Word(word="shit")],
        allowlist=["shift"],
    )
    user = WordList(
        words=[Word(word="fuck", threshold=90), Word(word="newword")],
        allowlist=["damage"],
    )

    merged = merge_wordlists(bundled, user)

    fuck_word = next(w for w in merged.words if w.word == "fuck")
    assert fuck_word.threshold == 90  # user overrides bundled
    assert {w.word for w in merged.words} == {"fuck", "shit", "newword"}
    assert set(merged.allowlist) == {"shift", "damage"}  # extended, not replaced


def test_merge_wordlists_no_user_returns_bundled_unchanged() -> None:
    bundled = WordList(words=[Word(word="fuck")], allowlist=["shift"])

    assert merge_wordlists(bundled, None) is bundled


def test_content_hash_stable_and_sensitive_to_changes() -> None:
    a = WordList(words=[Word(word="fuck")], allowlist=["shift"])
    b = WordList(words=[Word(word="fuck")], allowlist=["shift"])
    c = WordList(words=[Word(word="fuck", threshold=90)], allowlist=["shift"])

    assert a.content_hash == b.content_hash
    assert a.content_hash != c.content_hash
