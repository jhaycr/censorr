"""Filesystem utilities."""
import os
from pathlib import Path
from typing import Optional


def ensure_output_dir(output_dir: str) -> str:
    """Ensure output directory exists.
    
    Args:
        output_dir: Path to output directory
        
    Returns:
        Absolute path to output directory
    """
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return str(path.resolve())

