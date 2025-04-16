# Changelog

All notable changes to the vibectl project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Planned: Add basic logging features to vibectl for improved observability and debugging (WIP)
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

## [0.3.2] - 2025-04-15

### Added
- New `
