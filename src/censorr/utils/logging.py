"""Logging configuration utilities."""
import logging
from typing import Optional


def configure_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Configure a logger with timestamp formatting.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: DEBUG)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Only add handler if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return configure_logger(name)
