import argparse
import re
import subprocess
from enum import Enum
from pathlib import Path


class BumpType(str, Enum):
    patch = "patch"
    minor = "minor"
    major = "major"


def _parse_version(version: str) -> tuple[int, int, int]:
    major_s, minor_s, patch_s = version.split(".")
    return int(major_s), int(minor_s), int(patch_s)


def _bump_version(cur: tuple[int, int, int], bump: BumpType) -> tuple[int, int, int]:
    major, minor, patch = cur
    if bump == BumpType.major:
        return major + 1, 0, 0
    if bump == BumpType.minor:
        return major, minor + 1, 0
    return major, minor, patch + 1  # patch


def _update_pyproject(new_version: str, pyproject_path: Path) -> None:
    text = pyproject_path.read_text()
    updated = re.sub(
        r'version\s*=\s*"\d+\.\d+\.\d+"', f'version = "{new_version}"', text
    )
    pyproject_path.write_text(updated)


def _version_from_pyproject() -> str | None:
    """Return version string from pyproject.toml if present."""
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if pyproject_path.exists():
        for line in pyproject_path.read_text().splitlines():
            if line.strip().startswith("version") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"')
    return None


def get_version() -> str:
    """Return the project version.

    Priority:
    1. Version declared in pyproject.toml (source of truth for builds)
    2. Installed package metadata (editable installs or wheels already installed)
    """

    pj_ver = _version_from_pyproject()
    if pj_ver:
        return pj_ver

    # Fallback to runtime metadata
    try:
        from importlib import metadata

        return metadata.version("vibectl")
    except Exception:
        pass

    return "unknown"


def tag(version: str, dry_run: bool = True) -> None:
    """Create a git tag for the provided version.

    Args:
        version: Version string (e.g. "0.11.4").
        dry_run: If True, do not actually create the tag, just print the command.
    """
    tag_name = f"v{version}"
    cmd = ["git", "tag", tag_name]
    if dry_run:
        print("[dry-run]", " ".join(cmd))
    else:
        subprocess.check_call(cmd)
        print(f"Created git tag {tag_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="vibectl version utility")
    parser.add_argument(
        "--tag",
        action="store_true",
        help="Create a git tag for the current version (dry-run by default)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help=(
            "Push the tag to origin (implies --tag). Still dry-run unless --no-dry-run"
        ),
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Actually execute git commands (tag/push)",
    )
    parser.add_argument(
        "--bump",
        type=BumpType,
        choices=list(BumpType),
        help="Bump semantic version (patch/minor/major) and update pyproject.toml",
    )
    parser.set_defaults(dry_run=True)
    args = parser.parse_args()

    version = get_version()

    if args.bump:
        pj_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        cur_tup = _parse_version(version)
        new_tup = _bump_version(cur_tup, args.bump)
        new_version = ".".join(str(i) for i in new_tup)
        print(f"Current version: {version} -> New version: {new_version}")
        if args.dry_run:
            print("[dry-run] Would update pyproject.toml with new version")
        else:
            _update_pyproject(new_version, pj_path)
            print("Updated pyproject.toml with new version")
        # after bump, override variable for potential tagging
        version = new_version

    if args.tag or args.push:
        tag(version, dry_run=args.dry_run)
        if args.push:
            cmd = ["git", "push", "origin", f"v{version}"]
            if args.dry_run:
                print("[dry-run]", " ".join(cmd))
            else:
                subprocess.check_call(cmd)
                print(f"Pushed git tag v{version} to origin")
    else:
        print(version)


if __name__ == "__main__":
    main()
