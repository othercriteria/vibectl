import argparse
import subprocess
from pathlib import Path


def get_version() -> str:
    """Return the current vibectl version using importlib metadata fallback."""
    try:
        # Try runtime package metadata first (works in editable installs too)
        from importlib import metadata

        return metadata.version("vibectl")
    except Exception:
        # Fallback to parsing pyproject.toml (no external toml library dependency)
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        if pyproject_path.exists():
            for line in pyproject_path.read_text().splitlines():
                if line.strip().startswith("version") and "=" in line:
                    # version = "0.11.4"
                    return line.split("=", 1)[1].strip().strip('"')
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
    parser.set_defaults(dry_run=True)
    args = parser.parse_args()

    version = get_version()

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
