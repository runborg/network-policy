"""
Configuration loader with schema validation.

Loads TOML configuration files and validates them against the schema.
"""

import sys
from pathlib import Path
from typing import Any, Dict

try:
    import toml
except ImportError:
    print("Error: python3-toml not installed", file=sys.stderr)
    print("Install with: apt install python3-toml", file=sys.stderr)
    sys.exit(1)

from schema import validate_config, ValidationError
from logger import get_logger

logger = get_logger(__name__)


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load and validate TOML configuration file.
    
    Args:
        config_path: Path to TOML configuration file
        
    Returns:
        Validated configuration dictionary
        
    Raises:
        ValidationError: If configuration is invalid
        FileNotFoundError: If configuration file doesn't exist
        toml.TomlDecodeError: If TOML syntax is invalid
    """
    config_file = Path(config_path)
    
    # Check if file exists
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    # Load TOML file
    try:
        logger.debug(f"Loading configuration from {config_path}")
        with open(config_file, 'r') as f:
            config = toml.load(f)
    except toml.TomlDecodeError as e:
        raise ValidationError(f"Invalid TOML syntax: {e}")
    except Exception as e:
        raise ValidationError(f"Error reading configuration file: {e}")
    
    # Validate configuration
    logger.debug("Validating configuration")
    validate_config(config)
    
    logger.info(f"Configuration loaded successfully from {config_path}")
    return config


# Re-export ValidationError for convenience
__all__ = ["load_config", "ValidationError"]
