from censorr.audio.qc import evaluate_control_integrity, evaluate_over_mute_budgets, evaluate_window
from censorr.audio.windows import MuteWindow


def window(start_s: float, end_s: float) -> MuteWindow:
    return MuteWindow(start_s=start_s, end_s=end_s, source="entry_span", reason="matched_entry")


class TestEvaluateWindow:
    def test_silent_window_passes(self) -> None:
        w = window(1.0, 2.0)

        measurement, violation = evaluate_window(
            w, -90.0, control_db=-20.0, audio_min_drop_db=-12.0
        )

        assert measurement.is_silent is True
        assert violation is None

    def test_not_silent_enough_fails(self) -> None:
        w = window(1.0, 2.0)

        measurement, violation = evaluate_window(
            w, -22.0, control_db=-20.0, audio_min_drop_db=-12.0
        )

        assert measurement.is_silent is False
        assert violation is not None
        assert "not silent enough" in violation

    def test_boundary_exactly_at_drop_threshold_passes(self) -> None:
        w = window(1.0, 2.0)
        # control -20, drop -12 -> threshold is -32; exactly -32 should pass (<=)
        measurement, violation = evaluate_window(
            w, -32.0, control_db=-20.0, audio_min_drop_db=-12.0
        )

        assert measurement.is_silent is True
        assert violation is None


class TestEvaluateOverMuteBudgets:
    def test_within_budget_no_violations(self) -> None:
        windows = [window(1.0, 2.0)]  # 1s window
        mute_ratio, max_window, violations = evaluate_over_mute_budgets(
            windows, total_duration_s=100.0, max_mute_ratio=0.05, max_window_s=15.0
        )

        assert mute_ratio == 0.01
        assert max_window == 1.0
        assert violations == []

    def test_mute_ratio_over_budget_flagged(self) -> None:
        windows = [window(0.0, 10.0)]  # 10s window
        mute_ratio, _max_window, violations = evaluate_over_mute_budgets(
            windows, total_duration_s=100.0, max_mute_ratio=0.05, max_window_s=15.0
        )

        assert mute_ratio == 0.1
        assert any("mute ratio" in v for v in violations)

    def test_single_window_over_max_duration_flagged(self) -> None:
        windows = [window(0.0, 20.0)]
        _mute_ratio, max_window, violations = evaluate_over_mute_budgets(
            windows, total_duration_s=1000.0, max_mute_ratio=0.5, max_window_s=15.0
        )

        assert max_window == 20.0
        assert any("max window" in v for v in violations)

    def test_no_windows_zero_ratio(self) -> None:
        mute_ratio, max_window, violations = evaluate_over_mute_budgets(
            [], total_duration_s=100.0, max_mute_ratio=0.05, max_window_s=15.0
        )

        assert mute_ratio == 0.0
        assert max_window == 0.0
        assert violations == []

    def test_zero_duration_does_not_divide_by_zero(self) -> None:
        mute_ratio, _max_window, _violations = evaluate_over_mute_budgets(
            [window(0.0, 1.0)], total_duration_s=0.0, max_mute_ratio=0.05, max_window_s=15.0
        )

        assert mute_ratio == 0.0


class TestEvaluateControlIntegrity:
    def test_audible_control_samples_pass(self) -> None:
        ok, violations = evaluate_control_integrity([-20.0, -22.0, -18.0])

        assert ok is True
        assert violations == []

    def test_all_silent_control_samples_fail(self) -> None:
        ok, violations = evaluate_control_integrity([-91.0, -91.0, -91.0])

        assert ok is False
        assert len(violations) == 1

    def test_no_control_samples_fail(self) -> None:
        # e.g. mute windows cover the entire timeline -- no control region exists
        ok, violations = evaluate_control_integrity([])

        assert ok is False
        assert len(violations) == 1
