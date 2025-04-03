# vibectl

A vibes-based alternative to kubectl for interacting with Kubernetes clusters. Make
your cluster management more intuitive and fun!

## Features

- 🌟 Vibes-based interaction with Kubernetes clusters
- 🚀 Intuitive commands that just feel right
- 🎯 Simplified cluster management
- 🔍 Smart context awareness
- ✨ AI-powered summaries of cluster state

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
5. Install the Anthropic LLM provider:
   ```zsh
   llm install llm-anthropic
   ```
6. Configure your Anthropic API key:
   ```zsh
   export ANTHROPIC_API_KEY=your-api-key
   ```

The development environment will automatically:
- Create a virtual environment in `.venv` if it doesn't exist
- Activate the virtual environment
- Install the package in development mode with all dev dependencies

## Usage

Basic commands:

```zsh
# Display version information
vibectl version

# Show configuration
vibectl config show

# Set configuration values
vibectl config set <key> <value>

# Get resources with AI-powered summaries
vibectl get pods
vibectl get deployments -n kube-system
vibectl get pods --raw  # Show raw kubectl output too

# Describe resources with concise summaries
vibectl describe pod my-pod
vibectl describe deployment my-deployment -n kube-system
vibectl describe pod my-pod --raw  # Show raw kubectl output too

# Get container logs with smart summaries
vibectl logs pod/my-pod
vibectl logs deployment/my-deployment -n kube-system
vibectl logs pod/my-pod -c my-container --raw  # Show raw logs too

# Pass commands directly to kubectl
vibectl proxy <kubectl-commands>
```

### Configuration

You can customize vibectl's behavior with these configuration options:

```zsh
# Set a custom kubeconfig file
vibectl config set kubeconfig /path/to/kubeconfig

# Use a different LLM model (default: claude-3.7-sonnet)
vibectl config set llm_model your-preferred-model

# Always show raw kubectl output along with summaries
vibectl config set show_raw_output true
```

### Output Formatting

The `get`, `describe`, and `logs` commands provide AI-powered summaries using rich
text formatting:
- Resource names and counts in **bold**
- Healthy/good status in green
- Warnings in yellow
- Errors in red
- Kubernetes concepts (namespaces, etc.) in blue
- Timing information in *italics*

Example:
```
[bold]3 pods[/bold] in [blue]default namespace[/blue], all [green]Running[/green].
[bold]nginx-pod[/bold] [italic]running for 2 days[/italic].
[yellow]Warning: 2 pods have high restart counts[/yellow].
```

More commands coming soon!

## Project Structure

```
vibectl/                 # Root directory
├── .cursor/            # Cursor rules and configuration
│   └── rules/         # Cursor rule files (.mdc)
├── vibectl/           # Main package directory
│   ├── __init__.py   # Package initialization
│   ├── cli.py        # Command-line interface implementation
│   └── config.py     # Configuration management
├── tests/            # Test directory
│   ├── test_cli.py   # CLI tests
│   ├── test_config.py # Configuration tests
│   └── test_get.py   # Get command tests
├── flake.nix         # Nix flake configuration
├── flake.lock        # Nix flake lockfile
├── pyproject.toml    # Python project configuration and dependencies
├── .pre-commit-config.yaml # Pre-commit hooks configuration
├── Makefile          # Development automation
├── LICENSE           # MIT License
└── README.md         # This file
```

### Key Components

- **cli.py**: Implements the command-line interface and kubectl interactions
- **config.py**: Manages configuration storage and retrieval
- **tests/**: Contains pytest test files for each module
- **pyproject.toml**: Defines project metadata, dependencies, and tool configurations
- **.cursor/rules/**: Contains Cursor rules for development practices
- **flake.nix**: Defines the development environment

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

### Cursor Rules

This project uses Cursor rules (`.mdc` files in `.cursor/rules/`) to maintain
consistent development practices and automate common tasks. The rules system,
inspired by Geoffrey Huntley's [excellent blog post on building a Cursor
stdlib](https://ghuntley.com/stdlib/), helps enforce:

- Python virtual environment usage over Flake-managed dependencies
- Consistent rule file organization
- Project-specific conventions

Rules are stored in `.cursor/rules/` and include:
- `python-venv.mdc`: Enforces virtual environment usage for Python dependencies
- `rules.mdc`: Defines standards for rule file organization
- Additional rules as needed for project automation

The rules system acts as a "standard library" of development practices, helping
maintain consistency and automating repetitive tasks. Special thanks to Geoffrey
Huntley for sharing insights on effective Cursor rule usage.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file
for details.
