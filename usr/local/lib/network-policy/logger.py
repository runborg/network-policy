"""
Logging system with file and console handlers.

Provides centralized logging configuration with support for both file-based
and console output at configurable log levels.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    log_path: Optional[str] = None,
    log_level: str = "INFO",
    console: bool = True
) -> logging.Logger:
    """
    Configure logging with file and/or console handlers.
    
    Args:
        log_path: Path to log file. If None, only console logging is enabled.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console: Whether to enable console output
        
    Returns:
        Configured root logger
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear any existing handlers
    root_logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Add file handler if path provided
    if log_path:
        try:
            log_file = Path(log_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Use rotating file handler (10MB max, 5 backups)
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5
            )
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            sys.stderr.write(f"Warning: Could not setup file logging: {e}\n")
    
    # Add console handler if requested
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
