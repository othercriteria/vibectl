"""
Version compatibility checking for vibectl plugins.

This module provides functionality to check if a plugin's version requirements
are compatible with the current vibectl version.
"""

import re
from typing import NamedTuple

from vibectl import __version__


class VersionRange(NamedTuple):
    """Represents a version range requirement."""

    operator: str
    version: tuple[int, ...]


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string into a tuple of integers.

    Args:
        version_str: Version string like "1.2.3"

    Returns:
        Tuple of version components like (1, 2, 3)

    Raises:
        ValueError: If version string is invalid
    """
    try:
        return tuple(int(x) for x in version_str.split("."))
    except ValueError as e:
        raise ValueError(f"Invalid version format: {version_str}") from e


def parse_version_requirement(requirement: str) -> list[VersionRange]:
    """Parse a version requirement string into version ranges.

    Args:
        requirement: Version requirement like ">=1.0.0,<2.0.0"

    Returns:
        List of VersionRange objects

    Raises:
        ValueError: If requirement string is invalid
    """
    if not requirement.strip():
        raise ValueError("Empty version requirement")

    ranges = []

    # Split by commas and process each range
    for range_str in requirement.split(","):
        range_str = range_str.strip()
        if not range_str:
            continue

        # Match operator and version
        match = re.match(r"^(>=|<=|>|<|==|!=)(.+)$", range_str)
        if not match:
            raise ValueError(f"Invalid version range format: {range_str}")

        operator, version_str = match.groups()
        version_str = version_str.strip()

        try:
            version = parse_version(version_str)
        except ValueError as e:
            raise ValueError(f"Invalid version in range '{range_str}': {e}") from e

        ranges.append(VersionRange(operator, version))

    return ranges


def _normalize_versions(
    v1: tuple[int, ...], v2: tuple[int, ...]
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Normalize two version tuples to have the same length by padding with zeros."""
    max_len = max(len(v1), len(v2))
    v1_normalized = v1 + (0,) * (max_len - len(v1))
    v2_normalized = v2 + (0,) * (max_len - len(v2))
    return v1_normalized, v2_normalized


def check_version_compatibility(
    current_version: str, required_version: str
) -> tuple[bool, str]:
    """Check if current version satisfies the requirement.

    Args:
        current_version: Current vibectl version
        required_version: Required version range string

    Returns:
        Tuple of (is_compatible, error_message)
        If compatible, error_message is empty
    """
    try:
        current_ver = parse_version(current_version)
        required_ranges = parse_version_requirement(required_version)

        for range_req in required_ranges:
            operator = range_req.operator
            required_ver = range_req.version

            # Normalize versions to same length
            current_norm, required_norm = _normalize_versions(current_ver, required_ver)

            if operator == ">=":
                if not (current_norm >= required_norm):
                    return (
                        False,
                        f"Requires version >= {'.'.join(map(str, required_ver))}, "
                        f"got {current_version}",
                    )
            elif operator == "<=":
                if not (current_norm <= required_norm):
                    return (
                        False,
                        f"Requires version <= {'.'.join(map(str, required_ver))}, "
                        f"got {current_version}",
                    )
            elif operator == ">":
                if not (current_norm > required_norm):
                    return (
                        False,
                        f"Requires version > {'.'.join(map(str, required_ver))}, "
                        f"got {current_version}",
                    )
            elif operator == "<":
                if not (current_norm < required_norm):
                    return (
                        False,
                        f"Requires version < {'.'.join(map(str, required_ver))}, "
                        f"got {current_version}",
                    )
            elif operator == "==":
                if current_norm != required_norm:
                    return (
                        False,
                        f"Requires exact version {'.'.join(map(str, required_ver))}, "
                        f"got {current_version}",
                    )
            elif operator == "!=" and current_norm == required_norm:
                return (
                    False,
                    f"Incompatible with version "
                    f"{'.'.join(map(str, required_ver))}, "
                    f"got {current_version}",
                )

        return True, ""

    except ValueError as e:
        return False, f"Invalid version requirement format: {e}"


def check_plugin_compatibility(plugin_requirement: str) -> tuple[bool, str]:
    """Check if a plugin's version requirement is compatible with current vibectl.

    Args:
        plugin_requirement: Plugin's compatible_vibectl_versions string

    Returns:
        Tuple of (is_compatible, error_message)
    """
    return check_version_compatibility(__version__, plugin_requirement)
