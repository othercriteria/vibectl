# Testing Guide for vibectl

This document explains the testing approach, performance optimizations, and best practices for the vibectl project.

## Testing Overview

The project uses `pytest` for testing, with several additional plugins:
- `pytest-cov` for code coverage
- `pytest-xdist` for parallel test execution

## Test Performance Optimizations

### Performance Findings

Initial analysis identified several performance bottlenecks in the test suite:

1. **File I/O Operations**: Each test was performing multiple file operations via the `reset_memory` fixture
2. **No Parallelism**: Tests were running sequentially despite having no shared state
3. **Config Initialization**: Each test created new Config instances, resulting in excessive file operations

### Implemented Optimizations

#### 1. Memory Reset Optimization

The `reset_memory` fixture was optimized to:
- Use in-memory operations instead of file I/O for most tests
- Provide special handling for memory-specific tests that need actual file operations
- Skip memory reset entirely for tests marked with `@pytest.mark.fast`

```python
@pytest.fixture(autouse=True)
def reset_memory(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Reset memory between tests without file I/O."""
    # Skip for fast tests
    if request.node.get_closest_marker("fast"):
        yield
        return

    # Use actual file operations for memory-specific tests
    if "test_memory" in request.node.nodeid or "test_config" in request.node.nodeid:
        clear_memory()
        yield
        clear_memory()
        return

    # Use optimized in-memory approach for all other tests
    with patch("vibectl.config.Config._save_config"):
        from vibectl.config import Config
        config = Config()
        set_memory("", config)
        yield
```

#### 2. In-Memory Config Fixture

Added a special fixture for tests that need Config objects without file I/O:

```python
@pytest.fixture
def in_memory_config() -> Generator[Config, None, None]:
    """Create a Config instance that doesn't perform file I/O."""
    with patch.object(Config, '_save_config'), patch.object(Config, '_load_config'):
        config = Config()
        yield config
```

#### 3. Memory Mocking

Created a memory mock fixture for easy testing of memory operations:

```python
@pytest.fixture
def memory_mock() -> Generator[dict[str, Mock], None, None]:
    """Mock for memory functions to avoid file I/O operations in tests."""
    with patch("vibectl.memory.set_memory") as mock_set_memory, \
         patch("vibectl.memory.get_memory") as mock_get_memory, \
         patch("vibectl.memory.clear_memory") as mock_clear_memory, \
         patch("vibectl.memory.update_memory") as mock_update_memory:

        mock_get_memory.return_value = "Mocked memory content"

        yield {
            "set": mock_set_memory,
            "get": mock_get_memory,
            "clear": mock_clear_memory,
            "update": mock_update_memory,
        }
```

#### 4. Parallel Test Execution

Added support for running tests in parallel with `pytest-xdist`:

- Created a script at `scripts/run_parallel_tests.sh` that automatically determines optimal worker count
- Configured to run without coverage collection (due to compatibility issues between xdist and pytest-cov)
- Added Makefile targets for convenient execution

#### 5. Test Performance Categories

Added support for marking tests based on performance characteristics:

- `@pytest.mark.fast`: Tests that can run without memory reset (very fast)
- Regular tests: Most tests that benefit from the optimized memory reset
- Slow tests: Complex integration tests that need full memory functionality

## Usage

### Running Tests

Several options are available for running tests:

```bash
# Run all tests in parallel (default, faster)
make test

# Run all tests serially (slower but more compatible)
make test-serial

# Run only fast tests (fastest, for quick feedback)
make test-fast

# Run tests with detailed coverage report
make test-coverage
```

### Performance Comparison

| Test Mode | Time | Coverage | Use Case |
|-----------|------|----------|----------|
| Serial    | ~80s | Yes      | When parallel tests have issues |
| Parallel  | ~4s  | No       | Default for development (make test) |
| Fast-only | ~1s  | Limited  | Quick feedback during development |
| Coverage  | ~80s | Yes      | CI/CD, detailed analysis |

### Writing Optimized Tests

To create tests that run efficiently:

1. **Mark Fast Tests**:
   ```python
   @pytest.mark.fast
   def test_something_simple():
       """This test will run without memory reset."""
       assert True
   ```

2. **Use In-Memory Config**:
   ```python
   def test_with_config(in_memory_config):
       """This test will use an in-memory config without file I/O."""
       in_memory_config.set("key", "value")
       assert in_memory_config.get("key") == "value"
   ```

3. **Mock Memory Operations**:
   ```python
   def test_with_memory(memory_mock):
       """This test will use mocked memory functions."""
       # Configure the mock
       memory_mock["get"].return_value = "custom memory"

       # Use memory functions normally in code under test
       # All operations will use the mocks
   ```

## Best Practices

1. **Avoid File I/O in Tests**:
   - Use the provided fixtures to avoid actual file operations
   - Mock file operations when testing file-related functionality

2. **Use Appropriate Test Categories**:
   - Mark simple, isolated tests as `@pytest.mark.fast`
   - Use full integration tests only when necessary

3. **Run the Right Test Mode**:
   - Use `make test-fast` during active development for immediate feedback
   - Use `make test` (parallel) for validating all changes quickly
   - Use `make test-coverage` for detailed analysis and before committing

4. **Maintain Coverage**:
   - Even when using optimized test modes during development, always run full coverage checks before committing

## Troubleshooting

### Coverage and Parallel Testing

Running tests in parallel (`pytest-xdist`) is currently incompatible with collecting coverage data (`pytest-cov`). The incompatibility manifests as:

```
CoverageWarning: Module vibectl was previously imported, but not measured
```

To work around this:
- Use `make test` (parallel) for fast feedback without coverage
- Use `make test-coverage` when you need coverage data

### Fixture Incompatibilities

Some fixtures may not work correctly with parallelism. If you encounter issues:

1. Check if fixtures maintain isolated state
2. Ensure fixtures don't depend on global state
3. Use appropriate scope for fixtures (function, class, module, session)
