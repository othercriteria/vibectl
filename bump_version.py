#!/usr/bin/env python3
"""
Version bumping script for vibectl.

This script helps with incrementing the version number in pyproject.toml
using semantic versioning (major.minor.patch).

Note: Since vibectl now uses dynamic version resolution via get_package_version(),
only pyproject.toml needs to be updated. The __init__.py file automatically
gets the version from package metadata.
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

    # Update pyproject.toml (vibectl/__init__.py gets version dynamically)
    pyproject_updated = update_pyproject(args.file, new_version)

    if pyproject_updated:
        print(f"Successfully bumped version to {new_version_str} in pyproject.toml")
        print(
            "Note: __init__.py will automatically use the new version via "
            "get_package_version()"
        )
    else:
        print("Failed to update version.")
        return 1

    print("\nTo release this version:")
    print("  1. Update CHANGELOG.md:")
    print("     - Move 'Unreleased' changes to a new section:")
    print(f"       [{new_version_str}] - YYYY-MM-DD")
    print("     - Organize changes by type (Added, Changed, Fixed, etc.)")
    print("     - Add a fresh 'Unreleased' section at the top")
    print("  2. Commit the version changes:")
    print("     git commit -am 'chore: bump version to")
    print(f"     {new_version_str} and update changelog'")
    print("  3. Release to PyPI (using NixOS tools):")
    print("     pypi-dist all")
    print("     OR")
    print("     make pypi-release")
    return 0


if __name__ == "__main__":
    sys.exit(main())
