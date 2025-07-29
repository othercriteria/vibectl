# Publishing vibectl to PyPI

This document describes how to build and publish the vibectl package to PyPI,
with a focus on the NixOS-optimized workflow.

## Standard Makefile Workflow (Recommended)

The Makefile is the single source of truth for linting, tests, building, and
publishing to PyPI. All commands work the same whether you are in a Nix
`flake develop` shell or a plain virtual-env.

### Dry-run release (no upload)

```bash
make release            # builds wheel+sdist after full ci-check
```

### Publish to PyPI (with confirmation)

```bash
# Dry-run (default): shows twine upload and git tag commands
make publish

# Real upload + tag push
make publish PUBLISH_DRY_RUN=0
```

`make publish` does **not** bump the version for you.  When you need to update
the version:

```bash
# Update CHANGELOG first (script enforces this)
make bump-patch          # or bump-minor / bump-major
# If DRY_RUN=0 the version is written to pyproject.toml
```

After bump & changelog commit you can run `make release` to validate and
`make publish` to upload and tag.

---

## Manual fallback

If you prefer raw tools:

```bash
python -m build          # create dist/
twine upload dist/*      # upload (asks for credentials)
python scripts/version.py --tag --push --no-dry-run  # create/push git tag
```

But the Makefile targets above encapsulate the exact same steps with safety
checks and integration into CI.
