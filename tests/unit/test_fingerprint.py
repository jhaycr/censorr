import pytest

from censorr.config.schema import ResolvedConfig
from censorr.detect.wordlist import Word, WordList
from censorr.pipeline import fingerprint
from censorr.pipeline.fingerprint import compute_fingerprint


def base_kwargs() -> dict:
    return {
        "source_size": 1000,
        "source_mtime": 1700000000.0,
        "cfg": ResolvedConfig(),
        "wordlist": WordList(words=[Word(word="fuck")]),
    }


def test_same_inputs_produce_same_fingerprint() -> None:
    kwargs = base_kwargs()

    assert compute_fingerprint(**kwargs) == compute_fingerprint(**kwargs)


def test_different_source_size_changes_fingerprint() -> None:
    kwargs = base_kwargs()
    other = {**kwargs, "source_size": 2000}

    assert compute_fingerprint(**kwargs) != compute_fingerprint(**other)


def test_different_source_mtime_changes_fingerprint() -> None:
    kwargs = base_kwargs()
    other = {**kwargs, "source_mtime": 1700000001.0}

    assert compute_fingerprint(**kwargs) != compute_fingerprint(**other)


def test_different_settings_changes_fingerprint() -> None:
    kwargs = base_kwargs()
    other = {**kwargs, "cfg": ResolvedConfig(detect={"buffer_s": 0.5})}

    assert compute_fingerprint(**kwargs) != compute_fingerprint(**other)


def test_different_wordlist_content_changes_fingerprint() -> None:
    kwargs = base_kwargs()
    other = {**kwargs, "wordlist": WordList(words=[Word(word="shit")])}

    assert compute_fingerprint(**kwargs) != compute_fingerprint(**other)


def test_fingerprint_is_path_independent() -> None:
    # The function never takes a source path at all -- only stat values --
    # so two different host paths with identical size/mtime/settings/wordlist
    # (e.g. host vs. container views of the same file) fingerprint identically.
    kwargs = base_kwargs()

    assert compute_fingerprint(**kwargs) == compute_fingerprint(**base_kwargs())


def test_fingerprint_sensitive_to_app_version(monkeypatch: pytest.MonkeyPatch) -> None:
    kwargs = base_kwargs()
    before = compute_fingerprint(**kwargs)

    monkeypatch.setattr(fingerprint, "__version__", "999.0.0")
    after = compute_fingerprint(**kwargs)

    assert before != after
