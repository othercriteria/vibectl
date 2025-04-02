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
          ];

          shellHook = ''
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

            echo "Welcome to vibectl development environment!"
            echo "Python version: $(python --version)"
            echo "Virtual environment: $(which python)"
          '';
        };
      }
    );
}
