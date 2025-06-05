"""Tests for type definitions and utilities."""

from vibectl.types import (
    Fragment,
)


class TestFragment:
    """Test Fragment class functionality."""

    def test_fragment_creation(self) -> None:
        """Test basic fragment creation."""
        content = "Test content"
        fragment = Fragment(content)
        assert str(fragment) == content
