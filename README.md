# vibectl

A vibes-based alternative to kubectl for interacting with Kubernetes clusters. Make
your cluster management more intuitive and fun!

## Features

- 🌟 Vibes-based interaction with Kubernetes clusters
- 🚀 Intuitive commands that just feel right
- 🎯 Simplified cluster management
- 🔍 Smart context awareness
- ✨ AI-powered summaries of cluster state
- 🧠 Natural language resource queries

## Installation

1. Install [Flake](https://flake.build)
2. Clone and set up:
   ```zsh
   git clone https://github.com/yourusername/vibectl.git
   cd vibectl
   flake develop
   ```
3. Configure your Anthropic API key:
   ```zsh
   export ANTHROPIC_API_KEY=your-api-key
   ```

The development environment will automatically:
- Create and activate a Python virtual environment
- Install all dependencies including development tools
- Set up the Anthropic LLM provider

## Usage

Basic commands with AI-powered summaries:

```zsh
# Display version and configuration
vibectl version
vibectl config show

# Get resources
vibectl get pods                                    # List pods with summary
vibectl get vibe show me pods with high restarts   # Natural language query

# Create resources
vibectl create -f manifest.yaml                     # Create from file
vibectl create vibe an nginx pod with 3 replicas   # Natural language creation

# Describe resources
vibectl describe deployment my-app                  # Get detailed info
vibectl describe vibe tell me about the nginx pods  # Natural language query

# View logs
vibectl logs pod/my-pod                            # Get pod logs
vibectl logs vibe show errors from frontend pods   # Natural language query

# Direct kubectl access
vibectl just get pods                              # Pass directly to kubectl
```

### Configuration

```zsh
# Set a custom kubeconfig file
vibectl config set kubeconfig /path/to/kubeconfig

# Use a different LLM model (default: claude-3.7-sonnet)
vibectl config set llm_model your-preferred-model

# Always show raw kubectl output
vibectl config set show_raw_output true
```

### Output Formatting

Commands provide AI-powered summaries using rich text formatting:
- Resource names and counts in **bold**
- Healthy/good status in green
- Warnings in yellow
- Errors in red
- Kubernetes concepts in blue
- Timing information in *italics*

Example:
```
[bold]3 pods[/bold] in [blue]default namespace[/blue], all [green]Running[/green]
[bold]nginx-pod[/bold] [italic]running for 2 days[/italic]
[yellow]Warning: 2 pods have high restart counts[/yellow]
```

### Natural Language Support

The `vibe` subcommand supports natural language for all operations:

```zsh
# Find resources
vibectl get vibe show me pods in kube-system
vibectl get vibe find pods with high restart counts

# Create resources
vibectl create vibe a redis pod with persistent storage
vibectl create vibe a deployment with 3 nginx replicas

# Describe resources
vibectl describe vibe tell me about the nginx pods
vibectl describe vibe what's wrong with the database

# View logs
vibectl logs vibe show me recent errors
vibectl logs vibe what's happening in the api pods
```

## Project Structure

```
vibectl/                 # Root directory
├── .cursor/            # Cursor rules and configuration
│   └── rules/         # Cursor rule files (.mdc)
├── vibectl/           # Main package directory
│   ├── cli.py        # Command-line interface
│   ├── config.py     # Configuration management
│   └── prompt.py     # LLM prompt templates
├── tests/            # Test directory
├── flake.nix         # Development environment
└── README.md         # This file
```

## Development

This project uses [Flake](https://flake.build) for development environment
management. The environment is automatically set up when you run `flake develop`.

### Running Tests

```zsh
pytest
```

### Code Quality

The project uses pre-commit hooks for code quality, configured in
`.pre-commit-config.yaml`. These run automatically on commit and include:
- Black for code formatting
- isort for import sorting
- Flake8 for style guide enforcement
- MyPy for type checking

### Cursor Rules

The project uses Cursor rules (`.mdc` files in `.cursor/rules/`) to maintain
consistent development practices. These include:
- `python-venv.mdc`: Python virtual environment usage
- `rules.mdc`: Rule file organization standards
- `no-bazel.mdc`: Build system standards
- `autonomous-commits.mdc`: Commit automation

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file
for details.
