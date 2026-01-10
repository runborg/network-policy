"""
Network Policy Management System

A comprehensive network policy management system for embedded Linux with 
multiple interfaces, integrated firewall, health monitoring, and automatic failover.
"""

__version__ = "1.0.0"
__author__ = "Network Policy Team"
__license__ = "GPL-3.0"

# Package exports
from .logger import setup_logging, get_logger
from .config import load_config, ValidationError
from .schema import validate_config

__all__ = [
    "__version__",
    "setup_logging",
    "get_logger",
    "load_config",
    "validate_config",
    "ValidationError",
]
