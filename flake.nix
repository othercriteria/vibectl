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
            pkgs.uv            # uv: fast dependency resolver and lock generator
            pkgs.pre-commit   # pre-commit CLI for git hooks and manual runs
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

            # (make-only-release) Removed automatic virtualenv creation & hidden pip installs.

            echo "Welcome to vibectl development environment!"
            echo "Welcome to vibectl development environment!"

            # Re-add .venv bin directory to PATH if the virtualenv exists (needed for dmypy & other tools)
            if [ -d .venv ]; then
              export PATH="$(pwd)/.venv/bin:$PATH"
            fi
            # Show which vibectl will be used
            which vibectl || true
            echo "Python version: $(python --version)"
            echo "Virtual environment: $(which python)"
          '';
        };
      }
    );
}
