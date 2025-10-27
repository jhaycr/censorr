"""Audio utility functions for RMS calculation.

Provides RMS calculation for audio analysis without relying on the 
deprecated audioop module (removed in Python 3.13).
"""
import struct
import math


def rms(data: bytes, width: int) -> int:
    """Calculate RMS (Root Mean Square) of audio data.
    
    Args:
        data: Raw audio data as bytes
        width: Sample width in bytes (1, 2, or 4)
        
    Returns:
        RMS value as integer
        
    Raises:
        ValueError: If width is not supported or data is empty
    """
    if not data:
        return 0
    
    if width not in (1, 2, 4):
        raise ValueError(f"Unsupported sample width: {width}")
    
    if len(data) % width != 0:
        raise ValueError("Data length must be multiple of width")
    
    # Format string for struct unpacking
    if width == 1:
        fmt = 'B'  # unsigned char
        signed = False
    elif width == 2:
        fmt = 'h'  # signed short
        signed = True
    else:  # width == 4
        fmt = 'i'  # signed int
        signed = True
    
    # Unpack all samples
    sample_fmt = f'<{len(data) // width}{fmt}'
    samples = struct.unpack(sample_fmt, data)
    
    # Calculate RMS
    sum_squares = 0
    for sample in samples:
        # Convert unsigned to signed for calculation if needed
        if not signed and width == 1:
            sample = sample - 128
        
        sum_squares += sample * sample
    
    mean_square = sum_squares / len(samples)
    return int(math.sqrt(mean_square))