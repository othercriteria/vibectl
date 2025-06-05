"""
vibectl - A vibes-based alternative to kubectl
"""

from .utils import get_package_version

__version__ = get_package_version()


import logging

# Initialize package-level logger
logger = logging.getLogger("vibectl")
logger.setLevel(logging.INFO)  # Default level, can be overridden by config or CLI
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(levelname)s] %(message)s")
handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(handler)
