{
  description = "vibectl - A vibes-based alternative to kubectl";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python311;

        # Helper script for PyPI distribution tasks
        pypi-dist-script = pkgs.writeScriptBin "pypi-dist" ''
          #!/usr/bin/env bash

          set -e  # Exit on error

          # Show help menu
          function show_help() {
            echo "PyPI Distribution Helper for vibectl"
            echo ""
            echo "Commands:"
            echo "  build       - Build source and wheel distributions"
            echo "  test        - Test package in a clean environment"
            echo "  clean       - Remove build artifacts"
            echo "  testpypi    - Upload to TestPyPI"
            echo "  pypi        - Upload to PyPI"
            echo "  tag         - Create and push git tag for version"
            echo "  verify      - Verify version consistency"
            echo "  all         - Build, test, and upload to PyPI (with confirmation)"
            echo "  help        - Show this help message"
            echo ""
          }

          # Get version from pyproject.toml
          function get_version() {
            grep -Po '^version = "\K[^"]+' pyproject.toml
          }

          # Get version from __init__.py
          function get_init_version() {
            grep -Po '__version__ = "\K[^"]+' vibectl/__init__.py
          }

          # Verify version consistency between files
          function verify_version_consistency() {
            TOML_VERSION=$(get_version)
            INIT_VERSION=$(get_init_version)

            echo "Checking version consistency..."
            echo "pyproject.toml: $TOML_VERSION"
            echo "vibectl/__init__.py: $INIT_VERSION"

            if [ "$TOML_VERSION" != "$INIT_VERSION" ]; then
              echo "ERROR: Version mismatch detected!"
              echo "The version in pyproject.toml ($TOML_VERSION) does not match"
              echo "the __version__ in vibectl/__init__.py ($INIT_VERSION)"
              echo ""
              echo "Please update both files to have the same version."
              echo "You can use ./bump_version.py to update both files at once."
              return 1
            else
              echo "✅ Versions are consistent."
              return 0
            fi
          }

          # No args shows help
          if [ $# -eq 0 ]; then
            show_help
            exit 0
          fi

          # Process commands
          case "$1" in
            build)
              echo "Building package..."
              python -m build
              echo "Build complete. Artifacts in dist/ directory"
              ;;

            test)
              echo "Testing package in clean environment..."
              VERSION=$(get_version)

              # Create and activate test environment
              python -m venv test_env
              source test_env/bin/activate

              # Ensure wheel exists
              if [ ! -f "dist/vibectl-''${VERSION}-py3-none-any.whl" ]; then
                echo "Wheel not found. Building package..."
                python -m build
              fi

              # Install and test
              pip install dist/vibectl-''${VERSION}-py3-none-any.whl
              echo "Installing llm-anthropic..."
              pip install llm-anthropic
              echo "Testing vibectl command..."
              vibectl --version

              # Cleanup
              deactivate
              rm -rf test_env
              echo "Test complete"
              ;;

            clean)
              echo "Cleaning build artifacts..."
              rm -rf dist/ build/ *.egg-info test_env/
              echo "Clean complete"
              ;;

            testpypi)
              echo "Uploading to TestPyPI..."
              twine upload --repository-url https://test.pypi.org/legacy/ dist/*
              echo "Upload to TestPyPI complete"
              echo "Test install: pip install --index-url https://test.pypi.org/simple/ vibectl"
              ;;

            pypi)
              echo "Uploading to PyPI..."
              twine upload dist/*
              echo "Upload to PyPI complete"
              ;;

            tag)
              VERSION=$(get_version)
              echo "Creating and pushing git tag v''${VERSION}..."
              git tag "v''${VERSION}"
              git push origin "v''${VERSION}"
              echo "Tag created and pushed"
              ;;

            verify)
              verify_version_consistency
              ;;

            all)
              # Run full release process with confirmation
              VERSION=$(get_version)
              echo "Preparing to release vibectl v''${VERSION} to PyPI"
              echo "This will build, test, upload to PyPI, and tag the release."
              echo ""

              # Verify version consistency first
              if ! verify_version_consistency; then
                echo "Release aborted due to version inconsistency."
                exit 1
              fi

              read -p "Continue? (y/n) " -n 1 -r
              echo ""
              if [[ $REPLY =~ ^[Yy]$ ]]; then
                # Clean build artifacts but keep tests and linting artifacts
                rm -rf dist/ build/ *.egg-info test_env/

                # Run code quality checks without reinstalling
                echo "Running code quality checks..."
                pre-commit run --all-files
                mypy vibectl tests
                pytest -v

                # Build package
                echo "Building package..."
                python -m build

                # Test in a clean environment
                echo "Testing in clean environment..."
                python -m venv test_env
                source test_env/bin/activate
                pip install dist/vibectl-''${VERSION}-py3-none-any.whl
                pip install llm-anthropic
                vibectl --version
                deactivate
                rm -rf test_env

                # Upload to PyPI
                echo "Uploading to PyPI..."
                twine upload dist/*

                # Tag the release
                echo "Tagging release..."
                git tag "v''${VERSION}"
                git push origin "v''${VERSION}"

                echo "Release v''${VERSION} completed!"
              else
                echo "Release canceled."
              fi
              ;;

            help|--help|-h)
              show_help
              ;;

            *)
              echo "Unknown command: $1"
              show_help
              exit 1
              ;;
          esac
        '';

        # Helper script wrapper for bump_version.py
        bump-version-script = pkgs.writeScriptBin "bump-version" ''
          #!/usr/bin/env bash
          # Wrapper for bump_version.py script

          # Find the script in the current directory
          SCRIPT_PATH="$(dirname "$0")/../bump_version.py"

          if [ ! -f "$SCRIPT_PATH" ]; then
            SCRIPT_PATH="./bump_version.py"
          fi

          if [ ! -f "$SCRIPT_PATH" ]; then
            echo "Error: bump_version.py script not found"
            exit 1
          fi

          # Run the script with all arguments passed through
          python "$SCRIPT_PATH" "$@"
        '';
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            gnumake
            python
            python.pkgs.pip
            python.pkgs.virtualenv
            python.pkgs.setuptools
            python.pkgs.wheel
            python.pkgs.build  # for building packages
            python.pkgs.twine  # for uploading to PyPI
            pypi-dist-script   # custom distribution helper
            bump-version-script # version bumping helper
            gh  # GitHub CLI for interacting with GitHub
            docker
            docker-buildx
            # gRPC and Protocol Buffer tools
            protobuf
            protoc-gen-go
            grpcurl  # CLI tool for testing gRPC services
          ];

          shellHook = ''
            # Fix gRPC tools library loading issue in Nix
            export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH

            # Create virtualenv if it doesn't exist
            if [ ! -d .venv ]; then
              echo "Creating virtual environment..."
              virtualenv .venv
            fi

            # Activate virtualenv
            source .venv/bin/activate

            # Always install latest development dependencies
            echo "Installing development dependencies..."
            pip install -e ".[dev]"

            # Install Anthropic models for `llm`
            llm install llm-anthropic

            # Show help for distribution tools
            echo ""
            echo "🚀 Distribution tools available:"
            echo "  pypi-dist help     # Show PyPI distribution commands"
            echo "  bump-version patch # Bump the patch version (also: minor, major)"
            echo ""

            echo "Welcome to vibectl development environment!"
            echo "Python version: $(python --version)"
            echo "Virtual environment: $(which python)"
          '';
        };
      }
    );
}
