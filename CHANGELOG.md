# Changelog

All notable changes to the vibectl project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New `port-forward` command for forwarding Kubernetes service ports to local system
  - Basic implementation with support for all standard kubectl port-forward functionality
  - Rich progress display showing connection status and elapsed time
  - Support for vibe-based natural language requests
  - Notification for users when traffic monitoring via proxy is not configured
  - Suppressible warning via `warn_no_proxy` configuration option
- New `wait` command for waiting on specific conditions in Kubernetes
  - Basic implementation with support for all standard kubectl wait functionality
  - Support for vibe-based natural language requests
- Advanced port-forward features planned for future implementation:
  - Proxy layer for analyzing traffic through port-forward connections (Future)
  - Traffic metrics collection for improved troubleshooting (Future)
  - Extended options for port selection and service discovery (Future)
  - Background execution mode for long-running operations (Future)

### Changed
- Switched to asyncio for both `wait` and `port-forward` command implementation
  - Improves scalability for future features
  - Enables non-blocking progress displays
  - Prepares for more complex asynchronous operations

### Fixed
- Fixed tests for the `wait` command's live display feature
  - Properly mocked CLI and command handler modules
  - Resolved issues with asyncio coroutines in tests
- Fixed `port-forward vibe` command to use live display with connection status
  - Now shows the same live progress display as direct resource port-forward
  - Supports both `--live-display` and `--no-live-display` flags

## [0.3.1] - 2024-05-22

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

## [0.3.0] - 2025-05-01

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
