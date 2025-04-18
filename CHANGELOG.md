# Changelog

All notable changes to the vibectl project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New chaos-monkey demo in examples/k8s-sandbox featuring:
  - Red team vs. blue team competitive scenario
  - Blue agent for maintaining system stability
  - Red agent for simulating service disruptions
  - Metrics collection and performance evaluation
  - Containerized vibectl agents interacting with K8s cluster

## [0.4.0] - 2025-04-18

### Added
- Basic structured logging to vibectl for improved observability and debugging
  - Configurable log levels for different verbosity needs
  - Console and file output support
  - Structured logging for machine-readable output
- Configurable log level via config or VIBECTL_LOG_LEVEL environment variable
- User-facing warnings and errors are surfaced via the console
- Logging test pattern and fixtures for reliable assertions on log output

## [0.3.2] - 2025-04-15

### Added
- New `port-forward` command for Kubernetes service port forwarding
  - Supports standard kubectl port-forward functionality
  - Features rich progress display with connection status
  - Includes vibe-based natural language request support
  - Provides configurable proxy monitoring warnings
- New `wait` command for Kubernetes condition monitoring
  - Supports standard kubectl wait functionality
  - Includes vibe-based natural language request support

### Changed
- Implemented asyncio for `wait` and `port-forward` commands
  - Enables non-blocking progress displays and improves scalability
- Updated PLAN_VIBE_PROMPT to generate cleaner output
- Simplified command handling by removing prefix stripping logic

### Fixed
- Fixed `wait` command test suite for live display features
- Improved `port-forward vibe` command to show proper connection status
- Resolved `vibectl vibe` execution to prevent "unknown command" errors

## [0.3.1] - 2025-04-14

### Added
- K8s-sandbox example with challenge-based learning for Kubernetes
- Parameterizable difficulty levels for the K8s-sandbox demo
- Verbose mode option for the K8s-sandbox demo
- Heredoc handling for complex command processing

### Changed
- Bumped version from 0.3.0 to 0.3.1
- Improved K8s-sandbox architecture with overseer component
- Simplified command handling and argument parsing
- Enhanced test coverage for memory and output processor modules

### Fixed
- Improved K8s-sandbox challenge detection with direct Kind container access
- Resolved K8s-sandbox demo issues with API keys and poller detection
- Optimized slow tests in test_vibe_delete_confirm.py
- Fixed mock console handling in handle_vibe_request test
- Improved command processing for complex arguments with spaces
- Resolved line length errors in command handling
- Added tests/__init__.py to fix MyPy module detection

## [0.3.0] - 2025-04-12

### Added
- `show-kubectl` flag for controlling kubectl command display
- Model adapter pattern for more flexible LLM integrations
- Initial implementation for improved model selection and key management

### Fixed
- Handle kubeconfig flags and command structure correctly in handle_vibe_request
- Fix slow tests by properly mocking LLM calls
- Improve feature worktree rule to prevent file creation in main workspace
- Properly handle kubectl command output and error cases

### Changed
- Refactor code to use model adapter instead of direct LLM calls
- Extract API key message formatting into helper functions
- Update tests to work with OutputFlags object and new validation

## [0.2.2] - 2025-04-09

### Added
- Package distribution and versioning tools
- Complete PyPI distribution support
- Version management with `bump_version.py` script
- Makefile targets for release management

### Changed
- Bumped version from 0.2.1 to 0.2.2
- Aligned version numbers between pyproject.toml and __init__.py
