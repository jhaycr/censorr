"""Tests for audio utility functions."""
import pytest
import struct
import math
from src.utils.audio_utils import rms


class TestAudioUtils:
    """Test audio utility functions."""
    
    def test_rms_16bit_samples(self):
        """Test RMS calculation with 16-bit samples."""
        # Test data: samples [1000, -1000, 2000, -2000]
        data = struct.pack('<hhhh', 1000, -1000, 2000, -2000)
        
        result = rms(data, width=2)
        
        # Calculate expected RMS
        samples = [1000, -1000, 2000, -2000]
        sum_squares = sum(s * s for s in samples)
        expected = int(math.sqrt(sum_squares / len(samples)))
        
        assert result == expected
    
    def test_rms_8bit_samples(self):
        """Test RMS calculation with 8-bit samples."""
        # Test data: unsigned bytes [128, 200, 100, 150] (128 = zero for signed)
        data = struct.pack('<BBBB', 128, 200, 100, 150)
        
        result = rms(data, width=1)
        
        # Convert to signed for calculation: [0, 72, -28, 22]
        signed_samples = [128-128, 200-128, 100-128, 150-128]
        sum_squares = sum(s * s for s in signed_samples)
        expected = int(math.sqrt(sum_squares / len(signed_samples)))
        
        assert result == expected
    
    def test_rms_empty_data(self):
        """Test RMS with empty data."""
        assert rms(b'', width=2) == 0
    
    def test_rms_invalid_width(self):
        """Test RMS error handling for invalid width."""
        data = b'\x00\x01\x02\x03'
        
        with pytest.raises(ValueError, match="Unsupported sample width"):
            rms(data, width=3)
    
    def test_rms_invalid_data_length(self):
        """Test RMS error handling for invalid data length."""
        # 3 bytes for 16-bit samples (should be even)
        data = b'\x00\x01\x02'
        
        with pytest.raises(ValueError, match="Data length must be multiple"):
            rms(data, width=2)