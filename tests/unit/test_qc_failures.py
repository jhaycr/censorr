"""
DEPRECATED: This test file is no longer relevant.

QC functionality has been moved from subtitle_mask to separate operations:
- subtitle_qc: Quality control for subtitle files  
- audio_qc: Quality control for audio files

Tests for QC functionality should be in:
- tests/unit/test_subtitle_qc.py
- tests/unit/test_audio_qc.py

Tests for subtitle masking should be in:
- tests/unit/test_subtitle_mask.py
"""

import pytest


class TestDeprecatedQCTests:
    """Placeholder class to indicate this file is deprecated."""
    
    def test_qc_functionality_moved(self):
        """All QC tests have been moved to separate test files."""
        pytest.skip("QC functionality moved to subtitle_qc and audio_qc operations")
