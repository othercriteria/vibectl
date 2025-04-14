# Changelog

All notable changes to the vibectl project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2024-05-22

### Changed
- Bumped version from 0.3.0 to 0.3.1

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
