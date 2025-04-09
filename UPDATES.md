# PyPI Distribution Updates

This document summarizes changes made to support standard pip installation for
vibectl, making it more accessible for non-NixOS users, and to streamline the
PyPI distribution process for NixOS development.

## Changes Made

1. **Updated README.md**
   - Added pip-based installation instructions
   - Clearly separated standard and development installation options
   - Updated requirements section

2. **Updated pyproject.toml**
   - Added classifiers for better PyPI integration
   - Ensured correct metadata for PyPI listing

3. **Added py.typed marker file**
   - Created empty `vibectl/py.typed` file for proper typing support

4. **Created Distribution Documentation**
   - Added `DISTRIBUTION.md` with detailed instructions for publishing to PyPI
   - Documented both NixOS-specific and manual workflows

5. **Enhanced Nix Development Environment**
   - Added `pypi-dist` command to the devShell for PyPI operations
   - Added `bump-version` command for semantic versioning management
   - Configured Nix environment with all required PyPI tools

6. **Created Version Management Tools**
   - Added `bump_version.py` script for easy version bumping
   - Integrated version bumping into the Flake/Nix environment
   - Added comprehensive version management to the Makefile

7. **Updated Makefile for NixOS Integration**
   - Added PyPI distribution targets that use NixOS tools when available
   - Provided fallback mechanisms for non-NixOS environments
   - Added version bumping targets

8. **Updated STRUCTURE.md**
   - Added references to pip installation alongside Nix/Flake
   - Added information about PyPI distribution

## Usage Instructions

### For Users

Users can now install vibectl with a simple:

```zsh
pip install vibectl
pip install llm-anthropic
llm install llm-anthropic
export ANTHROPIC_API_KEY=your-api-key
```

### For Maintainers (NixOS)

In the NixOS development environment (`flake develop`), use:

1. **Version Management**:
   ```zsh
   # Bump patch version (0.0.X)
   bump-version patch

   # Or use the make target
   make bump-patch
   ```

2. **Complete PyPI Release Process**:
   ```zsh
   # One-command release with verification
   pypi-dist all

   # Or use the make target
   make pypi-release
   ```

3. **Individual Steps**:
   ```zsh
   # Build, test, upload separately
   pypi-dist build
   pypi-dist test
   pypi-dist pypi
   pypi-dist tag
   ```

See `DISTRIBUTION.md` for detailed instructions on both NixOS-specific and
manual workflows.
