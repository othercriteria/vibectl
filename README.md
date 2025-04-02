# vibectl

A vibes-based alternative to kubectl for interacting with Kubernetes clusters. Make 
your cluster management more intuitive and fun!

## Features

- 🌟 Vibes-based interaction with Kubernetes clusters
- 🚀 Intuitive commands that just feel right
- 🎯 Simplified cluster management
- 🔍 Smart context awareness

## Installation

1. Make sure you have [Python](https://python.org) 3.8+ installed
2. Install [Flake](https://flake.build)
3. Clone this repository:
   ```zsh
   git clone https://github.com/yourusername/vibectl.git
   cd vibectl
   ```
4. Set up the development environment:
   ```zsh
   flake develop
   ```

The development environment will automatically:
- Create a virtual environment in `.venv` if it doesn't exist
- Activate the virtual environment
- Install the package in development mode with all dev dependencies

## Usage

Coming soon!

## Development

This project uses Flake for development environment management and Python's virtual
environment for package isolation. The development environment is automatically set
up when you run `flake develop`.

### Manual Setup (if not using Flake)

1. Create and activate a virtual environment:
   ```zsh
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install development dependencies:
   ```zsh
   pip install -e ".[dev]"
   ```

### Running Tests

```zsh
pytest
```

### Code Quality

The project uses several tools to maintain code quality:
- Black for code formatting
- isort for import sorting
- Flake8 for style guide enforcement
- MyPy for type checking

Run them with:
```zsh
black .
isort .
flake8
mypy .
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file 
for details. 