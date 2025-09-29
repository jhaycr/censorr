"""Audio utility functions to replace deprecated audioop module.

Provides stereo-to-mono conversion and RMS calculation for audio analysis
without relying on the deprecated audioop module (removed in Python 3.13).
"""
import struct
import math


def tomono(data: bytes, width: int, left_factor: float = 0.5, right_factor: float = 0.5) -> bytes:
    """Convert stereo audio data to mono.
    
    Args:
        data: Raw stereo audio data as bytes
        width: Sample width in bytes (1, 2, or 4)
        left_factor: Weight for left channel (default 0.5)
        right_factor: Weight for right channel (default 0.5)
        
    Returns:
        Mono audio data as bytes
        
    Raises:
        ValueError: If width is not supported or data length is invalid
    """
    if width not in (1, 2, 4):
        raise ValueError(f"Unsupported sample width: {width}")
    
    if len(data) % (2 * width) != 0:
        raise ValueError("Data length must be multiple of 2 * width for stereo")
    
    # Format strings for struct packing/unpacking
    if width == 1:
        fmt = 'B'  # unsigned char
        signed = False
    elif width == 2:
        fmt = 'h'  # signed short
        signed = True
    else:  # width == 4
        fmt = 'i'  # signed int
        signed = True
    
    # Unpack stereo samples
    stereo_fmt = f'<{len(data) // width}{fmt}'
    samples = struct.unpack(stereo_fmt, data)
    
    # Convert pairs to mono
    mono_samples = []
    for i in range(0, len(samples), 2):
        left = samples[i]
        right = samples[i + 1]
        
        # Convert unsigned to signed for calculation if needed
        if not signed and width == 1:
            left = left - 128
            right = right - 128
        
        # Mix channels
        mono = int(left * left_factor + right * right_factor)
        
        # Convert back to unsigned if needed
        if not signed and width == 1:
            mono = max(0, min(255, mono + 128))
        
        mono_samples.append(mono)
    
    # Pack mono samples
    mono_fmt = f'<{len(mono_samples)}{fmt}'
    return struct.pack(mono_fmt, *mono_samples)


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