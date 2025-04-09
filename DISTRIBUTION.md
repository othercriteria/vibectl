# Publishing vibectl to PyPI

This document describes how to build and publish the vibectl package to PyPI,
with a focus on the NixOS-optimized workflow.

## NixOS/Flake-based Workflow (Recommended)

The project includes built-in Nix tools for handling the PyPI distribution process.
These tools are automatically available in the development shell.

### Using the `pypi-dist` Command

When in the Nix development shell (`flake develop`), you have access to the
`pypi-dist` command:

```zsh
# Show available commands
pypi-dist help

# Build package
pypi-dist build

# Test in isolated environment
pypi-dist test

# Upload to TestPyPI
pypi-dist testpypi

# Upload to PyPI
pypi-dist pypi

# Tag the release in git
pypi-dist tag

# Verify version consistency
pypi-dist verify

# Complete release process (build, test, upload, tag)
pypi-dist all
```

The `pypi-dist all` command is the recommended approach for releasing, as it:
1. Runs code quality checks without reinstallation conflicts
2. Builds the package freshly
3. Tests in a clean environment
4. Uploads to PyPI
5. Creates and pushes git tags

### Using Makefile Targets

Alternatively, you can use the Makefile targets which will leverage the `pypi-dist`
command when available:

```zsh
# Build package
make pypi-build

# Test in isolated environment
make pypi-test

# Upload to PyPI
make pypi-upload

# Complete release process (with quality checks)
make pypi-release
```

The `make pypi-release` target runs all quality checks, builds the package, tests
it, uploads to PyPI, and creates a git tag.

> **Note**: If you encounter installation conflicts during `make pypi-release`,
> try using `pypi-dist all` instead, which uses a more robust approach to avoid
> reinstallation issues in the development environment.

## Manual Process (Alternative)

If you need to perform the process manually, follow these steps:

### Prerequisites

You'll need the following tools:
- Python 3.10+
- pip
- build
- twine

Install the required tools:

```zsh
pip install build twine
```

### Building the Package

1. Make sure the version in `pyproject.toml` is updated.

2. Build the package:

```zsh
python -m build
```

This will create both source distribution (.tar.gz) and wheel (.whl) in the `dist/` directory.

### Testing the Package

Before uploading to PyPI, you might want to test the package:

1. Create a virtual environment:

```zsh
python -m venv test_env
source test_env/bin/activate
```

2. Install the package from the dist directory:

```zsh
pip install dist/vibectl-*.whl
```

3. Test that the package works:

```zsh
pip install llm-anthropic
vibectl --version
```

4. Deactivate the virtual environment when done:

```zsh
deactivate
```

### Publishing to TestPyPI (Optional)

Before publishing to the main PyPI index, you can test the upload process on TestPyPI:

```zsh
twine upload --repository-url https://test.pypi.org/legacy/ dist/*
```

Then install from TestPyPI to test:

```zsh
pip install --index-url https://test.pypi.org/simple/ vibectl
```

### Publishing to PyPI

To upload the package to the main PyPI index:

```zsh
twine upload dist/*
```

You'll be prompted for your PyPI username and password.

### Post-Publishing Tasks

After successful publishing:

1. Create a new Git tag for the version:

```zsh
git tag v$(grep -Po '^version = "\K[^"]+' pyproject.toml)
git push origin v$(grep -Po '^version = "\K[^"]+' pyproject.toml)
```

2. Clean up build artifacts:

```zsh
rm -rf dist/ build/ *.egg-info
```

## Version Management

When updating the package on PyPI:

1. Update the version in `pyproject.toml`
2. Make your changes
3. Use one of the workflows above to publish

> **Note**: Always use the `bump-version` command to update versions, as it will
> automatically update both `pyproject.toml` and `vibectl/__init__.py` to keep them
> in sync. Running `bump-version patch|minor|major` will handle this for you.

## Troubleshooting

### Version Inconsistency

If you encounter errors about version inconsistency, it means the version in
`pyproject.toml` doesn't match the `__version__` in `vibectl/__init__.py`. To fix this:

```zsh
# Check the inconsistency
pypi-dist verify

# Fix by using bump-version to set both files to the same version
# or manually edit vibectl/__init__.py to match pyproject.toml
```

The `pypi-dist all` command automatically checks for version consistency before
proceeding with the release process.

### Installation Conflicts

If you encounter errors during the release process that involve package installation
conflicts (such as `uninstall-no-record-file` or similar errors), try these alternatives:

1. Use `pypi-dist all` instead of `make pypi-release`
2. Run the release steps manually:
   ```zsh
   make clean
   make pypi-check  # Runs checks without reinstalling
   make pypi-build
   make pypi-test
   make pypi-upload
   VERSION=$(grep -Po '^version = "\K[^"]+' pyproject.toml)
   git tag "v$VERSION"
   git push origin "v$VERSION"
   ```
