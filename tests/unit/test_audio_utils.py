"""Tests for audio utility functions."""
import pytest
import struct
import math
from src.utils.audio_utils import tomono, rms


class TestAudioUtils:
    """Test audio utility functions."""
    
    def test_tomono_16bit_stereo(self):
        """Test stereo to mono conversion with 16-bit samples."""
        # Create stereo test data: left=1000, right=2000 (signed shorts)
        left = 1000
        right = 2000
        stereo_data = struct.pack('<hh', left, right)
        
        # Convert to mono with equal weighting
        mono_data = tomono(stereo_data, width=2, left_factor=0.5, right_factor=0.5)
        
        # Unpack result
        mono_sample = struct.unpack('<h', mono_data)[0]
        expected = int(left * 0.5 + right * 0.5)  # 1500
        
        assert mono_sample == expected
    
    def test_tomono_8bit_stereo(self):
        """Test stereo to mono conversion with 8-bit samples."""
        # Create stereo test data: left=100, right=200 (unsigned chars)
        left = 100
        right = 200
        stereo_data = struct.pack('<BB', left, right)
        
        # Convert to mono
        mono_data = tomono(stereo_data, width=1)
        
        # Unpack result
        mono_sample = struct.unpack('<B', mono_data)[0]
        # For 8-bit: convert to signed, mix, convert back
        expected = int((left - 128) * 0.5 + (right - 128) * 0.5) + 128  # 150
        
        assert mono_sample == expected
    
    def test_tomono_multiple_samples(self):
        """Test stereo to mono with multiple sample pairs."""
        # Two stereo sample pairs
        stereo_data = struct.pack('<hhhh', 1000, 2000, 3000, 4000)
        
        mono_data = tomono(stereo_data, width=2)
        
        # Should get two mono samples
        mono_samples = struct.unpack('<hh', mono_data)
        assert mono_samples[0] == 1500  # (1000 + 2000) / 2
        assert mono_samples[1] == 3500  # (3000 + 4000) / 2
    
    def test_tomono_invalid_width(self):
        """Test error handling for invalid sample width."""
        data = b'\x00\x01\x02\x03'
        
        with pytest.raises(ValueError, match="Unsupported sample width"):
            tomono(data, width=3)
    
    def test_tomono_invalid_data_length(self):
        """Test error handling for invalid data length."""
        # Odd number of bytes for 16-bit stereo
        data = b'\x00\x01\x02'
        
        with pytest.raises(ValueError, match="Data length must be multiple"):
            tomono(data, width=2)
    
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
    
    def test_compatibility_with_simple_case(self):
        """Test that results are reasonable for simple known case."""
        # Simple test case: single 16-bit stereo sample
        stereo_sample = struct.pack('<hh', 16000, 8000)
        
        # Convert to mono
        mono_data = tomono(stereo_sample, width=2)
        mono_value = struct.unpack('<h', mono_data)[0]
        assert mono_value == 12000  # (16000 + 8000) / 2
        
        # Calculate RMS of mono sample
        rms_value = rms(mono_data, width=2)
        assert rms_value == 12000  # RMS of single sample is the sample itself