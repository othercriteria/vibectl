"""Configuration management for vibectl"""

import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any

DEFAULT_CONFIG = {
    "kubeconfig": None,  # Will use default kubectl config location if None
}

class Config:
    """Manages vibectl configuration"""
    
    def __init__(self) -> None:
        self.config_dir = self._get_config_dir()
        self.config_file = self.config_dir / "config.yaml"
        self.config = self._load_config()

    def _get_config_dir(self) -> Path:
        """Get the config directory following XDG convention"""
        xdg_config_home = os.environ.get(
            "XDG_CONFIG_HOME", 
            os.path.expanduser("~/.config")
        )
        config_dir = Path(xdg_config_home) / "vibectl"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        if not self.config_file.exists():
            return DEFAULT_CONFIG.copy()
        
        with open(self.config_file, 'r') as f:
            loaded_config = yaml.safe_load(f) or {}
            config = DEFAULT_CONFIG.copy()
            config.update(loaded_config)
            return config

    def save(self) -> None:
        """Save current configuration to file"""
        with open(self.config_file, 'w') as f:
            yaml.dump(self.config, f)

    def get(self, key: str) -> Any:
        """Get a configuration value"""
        return self.config.get(key)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value"""
        self.config[key] = value
        self.save()

    def show(self) -> Dict[str, Any]:
        """Return the current configuration"""
        return self.config 