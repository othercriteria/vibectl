# Planned Changes – uv-based dependency locking

- Add uv to development dependencies (pyproject.toml `[project.optional-dependencies].dev`)
- Generate and commit `uv.lock` using `uv pip compile --extra=dev`
- Update `flake.nix` devShell to include `pkgs.uv`
- Add `lock` target to Makefile to regenerate the lock file
- Document workflow in STRUCTURE.md / TESTING.md
