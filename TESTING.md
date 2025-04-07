# Testing Strategy for Vibectl

This document outlines the testing approach for the Vibectl project, including types
of tests, test coverage goals, and best practices.

## Testing Goals

- Maintain high test coverage (aim for 100% with documented exceptions)
- Ensure all CLI commands and options work as expected
- Prevent regressions when adding new features
- Ensure error handling is robust and tested
- Isolate tests from actual system resources (kubectl, LLM APIs)

## Test Types

### Unit Tests

Unit tests focus on testing individual components in isolation:

- **Component Tests**: Test individual modules like `config.py`, `console.py`, etc.
- **CLI Command Tests**: Test each CLI command's functionality
- **Error Handling Tests**: Ensure proper handling of edge cases and errors

### Integration Tests

Integration tests verify interactions between components:

- **End-to-End CLI Tests**: Test full CLI command flow
- **Configuration Integration**: Test config components work together
- **Output Processing Pipeline**: Test the output processing workflow

## Test Structure

Tests are organized following these principles:

1. One test file per main component (e.g., `test_config.py` for `config.py`)
2. Dedicated test files for each main CLI command (e.g., `test_cli_get.py`)
3. Common fixtures in `conftest.py`
4. All tests independent from real system resources using mocks

## Testing Best Practices

### Use of Fixtures

- Use pytest fixtures for common setup
- Create dedicated fixtures for complex mock setups
- Reuse fixtures across test files when appropriate
- Document fixtures with clear docstrings

### Mocking

- Mock all external dependencies:
  - `kubectl` calls (use `mock_run_kubectl`)
  - LLM API calls (use `mock_llm`)
  - File system operations when appropriate
- Use appropriate scope for mocks (function, class, module)
- Verify mock calls to ensure correct interaction

### Parameterized Testing

- Use pytest's parameterize feature for testing multiple inputs
- Reduce duplication by parameterizing similar test cases
- Include edge cases in parameterized tests

### Test Coverage

- Aim for 100% code coverage
- Document any excluded areas with reasons
- Focus on testing logic rather than just lines
- Include edge cases and error conditions

## Test Workflow

### Local Testing

Run tests locally with:

```bash
make test          # Run all tests
make test-coverage # Run tests with coverage report
```

### CI/CD Integration

Tests run automatically on:
- Pull requests
- Pushes to main branch
- Release creation

Coverage reports are generated and published to track progress.

## Test Naming Conventions

- Test files: `test_*.py`
- Test functions: `test_*`
- Test classes: `Test*`
- Use descriptive names that explain what's being tested
- Include the expected behavior in the name

Example: `test_config_handles_missing_file`

## Future Test Improvements

- Add property-based testing for complex logic
- Implement integration tests with Docker-based Kubernetes
- Add performance benchmarking for key operations
- Implement snapshot testing for complex outputs
