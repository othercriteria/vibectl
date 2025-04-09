#!/usr/bin/env python3
"""
Version bumping script for vibectl.

This script helps with incrementing the version number in pyproject.toml
using semantic versioning (major.minor.patch).
"""

import argparse
import re
import sys
from enum import Enum
from pathlib import Path


class BumpType(str, Enum):
    """Types of version bumps following semantic versioning."""

    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


def get_current_version(pyproject_path: Path) -> tuple[int, int, int] | None:
    """Extract the current version from pyproject.toml."""
    if not pyproject_path.exists():
        print(f"Error: {pyproject_path} not found.")
        return None

    content = pyproject_path.read_text()
    version_match = re.search(r'version\s*=\s*"(\d+)\.(\d+)\.(\d+)"', content)

    if not version_match:
        print("Error: Could not find version in pyproject.toml.")
        return None

    return (
        int(version_match.group(1)),
        int(version_match.group(2)),
        int(version_match.group(3)),
    )


def bump_version(
    current_version: tuple[int, int, int], bump_type: BumpType
) -> tuple[int, int, int]:
    """Increment the version based on the bump type."""
    major, minor, patch = current_version

    if bump_type == BumpType.MAJOR:
        return (major + 1, 0, 0)
    elif bump_type == BumpType.MINOR:
        return (major, minor + 1, 0)
    else:  # PATCH
        return (major, minor, patch + 1)


def update_pyproject(pyproject_path: Path, new_version: tuple[int, int, int]) -> bool:
    """Update the version in pyproject.toml."""
    content = pyproject_path.read_text()
    major, minor, patch = new_version
    new_version_str = f"{major}.{minor}.{patch}"

    updated_content = re.sub(
        r'version\s*=\s*"\d+\.\d+\.\d+"',
        f'version = "{new_version_str}"',
        content,
    )

    pyproject_path.write_text(updated_content)
    return True


def update_init_file(init_path: Path, new_version: tuple[int, int, int]) -> bool:
    """Update the __version__ variable in __init__.py."""
    if not init_path.exists():
        print(f"Warning: {init_path} not found. Skipping __version__ update.")
        return False

    content = init_path.read_text()
    major, minor, patch = new_version
    new_version_str = f"{major}.{minor}.{patch}"

    updated_content = re.sub(
        r'__version__\s*=\s*"\d+\.\d+\.\d+"',
        f'__version__ = "{new_version_str}"',
        content,
    )

    # Check if a replacement was made
    if updated_content == content:
        print(f"Warning: Could not find __version__ pattern in {init_path}.")
        return False

    init_path.write_text(updated_content)
    return True


def main() -> int:
    """Run the version bumping process."""
    parser = argparse.ArgumentParser(description="Bump vibectl version")
    parser.add_argument(
        "bump_type",
        type=BumpType,
        choices=list(BumpType),
        help="Type of version bump to perform",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to pyproject.toml (default: ./pyproject.toml)",
    )

    args = parser.parse_args()

    current_version = get_current_version(args.file)
    if not current_version:
        return 1

    current_version_str = ".".join(str(v) for v in current_version)
    print(f"Current version: {current_version_str}")

    new_version = bump_version(current_version, args.bump_type)
    new_version_str = ".".join(str(v) for v in new_version)
    print(f"New version: {new_version_str}")

    if args.dry_run:
        print("Dry run - no changes made.")
        return 0

    # Path to __init__.py relative to pyproject.toml
    init_path = args.file.parent / "vibectl" / "__init__.py"

    # Update both files
    pyproject_updated = update_pyproject(args.file, new_version)
    init_updated = update_init_file(init_path, new_version)

    if pyproject_updated and init_updated:
        print(f"Successfully bumped version to {new_version_str} in both files")
    elif pyproject_updated:
        print(f"Updated version in pyproject.toml to {new_version_str}")
        print("Warning: Failed to update __init__.py")
    else:
        print("Failed to update version.")
        return 1

    print("\nTo release this version:")
    print("  1. Commit the version change:")
    print(f"     git commit -am 'chore: bump version to {new_version_str}'")
    print("  2. Release to PyPI (using NixOS tools):")
    print("     pypi-dist all")
    print("     OR")
    print("     make pypi-release")
    return 0


if __name__ == "__main__":
    sys.exit(main())
