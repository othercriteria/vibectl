"""Configuration management for vibectl"""

import os
from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULT_CONFIG = {
    "kubeconfig": None,  # Will use default kubectl config location if None
}


class Config:
    """Manages vibectl configuration"""

    def __init__(self) -> None:
        """Initialize configuration."""
        self.config_dir = (
            Path(os.getenv("XDG_CONFIG_HOME", "~/.config")).expanduser() / "vibectl"
        )
        self.config_file = self.config_dir / "config.yaml"
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            if not self.config_dir.exists():
                self.config_dir.mkdir(parents=True)
            if self.config_file.exists():
                with open(self.config_file) as f:
                    self._config = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            self._config = {}

    def save(self) -> None:
        """Save current configuration to file"""
        try:
            with open(self.config_file, "w") as f:
                yaml.dump(self._config, f)
        except OSError:
            # Log error or handle it appropriately
            # For now, we'll just let it propagate since this is a write operation
            raise

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            key: The configuration key
            default: Default value if key is not found

        Returns:
            The configuration value or default if not found
        """
        return self._config.get(key, default)

    def set(self, key: str, value: str) -> None:
        """Set a configuration value.

        Args:
            key: The configuration key
            value: The value to set
        """
        self._config[key] = value
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            yaml.dump(self._config, f)

    def show(self) -> Dict[str, Any]:
        """Show all configuration values.

        Returns:
            Dictionary of all configuration values
        """
        return dict(self._config)
