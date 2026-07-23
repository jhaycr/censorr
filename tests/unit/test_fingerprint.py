import pytest

from censorr.config.schema import ResolvedConfig
from censorr.pipeline import fingerprint
from censorr.pipeline.fingerprint import compute_fingerprint, compute_plan_hash


def base_kwargs() -> dict:
    return {
        "source_size": 1000,
        "source_mtime": 1700000000.0,
        "cfg": ResolvedConfig(),
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


def test_service_settings_do_not_change_fingerprint() -> None:
    # Queue paths/TTLs can't affect output content -- moving the queue
    # directory must not force a full-library reprocess.
    kwargs = base_kwargs()
    other = {**kwargs, "cfg": ResolvedConfig(service={"queue_path": "/elsewhere/queue"})}

    assert compute_fingerprint(**kwargs) == compute_fingerprint(**other)


def test_wordlist_does_not_change_base_fingerprint() -> None:
    # Option 4: the wordlist is intentionally out of the base fingerprint --
    # its per-file effect is captured by the plan hash instead, so editing the
    # list doesn't blanket-invalidate the library.
    kwargs = base_kwargs()
    other = {**kwargs, "cfg": ResolvedConfig(detect={"wordlist": "/some/other.json"})}

    assert compute_fingerprint(**kwargs) == compute_fingerprint(**other)


def test_fingerprint_is_path_independent() -> None:
    # The function never takes a source path at all -- only stat values --
    # so two different host paths with identical size/mtime/settings (e.g. host
    # vs. container views of the same file) fingerprint identically.
    kwargs = base_kwargs()

    assert compute_fingerprint(**kwargs) == compute_fingerprint(**base_kwargs())


def test_fingerprint_sensitive_to_app_version(monkeypatch: pytest.MonkeyPatch) -> None:
    kwargs = base_kwargs()
    before = compute_fingerprint(**kwargs)

    monkeypatch.setattr(fingerprint, "__version__", "999.0.0")
    after = compute_fingerprint(**kwargs)

    assert before != after


class TestPlanHash:
    def _plan(self, **overrides: object) -> str:
        kwargs: dict = {
            "mode": "full",
            "outcome": None,
            "windows": [(2.0, 3.0), (6.0, 7.5)],
            "masked_entries": [(2.0, 3.0, "a ****"), (6.0, 7.5, "the ****")],
            "captions_entries": [],
        }
        kwargs.update(overrides)
        return compute_plan_hash(**kwargs)  # type: ignore[arg-type]

    def test_identical_plans_hash_equal(self) -> None:
        assert self._plan() == self._plan()

    def test_window_ordering_does_not_matter(self) -> None:
        assert self._plan() == self._plan(windows=[(6.0, 7.5), (2.0, 3.0)])

    def test_different_windows_change_hash(self) -> None:
        assert self._plan() != self._plan(windows=[(2.0, 3.0)])

    def test_different_masked_text_changes_hash(self) -> None:
        assert self._plan() != self._plan(
            masked_entries=[(2.0, 3.0, "a ****"), (6.0, 7.5, "the shit")]
        )

    def test_mode_and_outcome_change_hash(self) -> None:
        assert self._plan() != self._plan(mode="clean")
        assert self._plan() != self._plan(outcome="skipped_clean")
