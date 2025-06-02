"""
Tests for version compatibility checking functionality.

This module tests the version parsing, comparison, and compatibility checking
logic used for plugin installation validation.
"""

from unittest.mock import patch

import pytest

from vibectl.version_compat import (
    VersionRange,
    check_plugin_compatibility,
    check_version_compatibility,
    parse_version,
    parse_version_requirement,
)


class TestVersionParsing:
    """Tests for version string parsing."""

    def test_parse_simple_version(self) -> None:
        """Test parsing simple version strings."""
        assert parse_version("1.0.0") == (1, 0, 0)
        assert parse_version("2.5.3") == (2, 5, 3)
        assert parse_version("0.8.7") == (0, 8, 7)

    def test_parse_version_with_different_lengths(self) -> None:
        """Test parsing versions with different numbers of components."""
        assert parse_version("1.0") == (1, 0)
        assert parse_version("1") == (1,)
        assert parse_version("1.2.3.4") == (1, 2, 3, 4)

    def test_parse_invalid_version(self) -> None:
        """Test parsing invalid version strings."""
        with pytest.raises(ValueError, match="Invalid version format"):
            parse_version("1.0.a")

        with pytest.raises(ValueError, match="Invalid version format"):
            parse_version("1..0")

        with pytest.raises(ValueError, match="Invalid version format"):
            parse_version("")


class TestVersionRequirementParsing:
    """Tests for version requirement parsing."""

    def test_parse_single_requirement(self) -> None:
        """Test parsing single version requirements."""
        ranges = parse_version_requirement(">=1.0.0")
        assert len(ranges) == 1
        assert ranges[0] == VersionRange(">=", (1, 0, 0))

    def test_parse_multiple_requirements(self) -> None:
        """Test parsing multiple version requirements."""
        ranges = parse_version_requirement(">=1.0.0,<2.0.0")
        assert len(ranges) == 2
        assert ranges[0] == VersionRange(">=", (1, 0, 0))
        assert ranges[1] == VersionRange("<", (2, 0, 0))

    def test_parse_all_operators(self) -> None:
        """Test parsing all supported operators."""
        test_cases = [
            (">=1.0.0", ">=", (1, 0, 0)),
            ("<=1.0.0", "<=", (1, 0, 0)),
            (">1.0.0", ">", (1, 0, 0)),
            ("<1.0.0", "<", (1, 0, 0)),
            ("==1.0.0", "==", (1, 0, 0)),
            ("!=1.0.0", "!=", (1, 0, 0)),
        ]

        for req_str, expected_op, expected_ver in test_cases:
            ranges = parse_version_requirement(req_str)
            assert len(ranges) == 1
            assert ranges[0] == VersionRange(expected_op, expected_ver)

    def test_parse_with_whitespace(self) -> None:
        """Test parsing requirements with whitespace."""
        ranges = parse_version_requirement(" >= 1.0.0 , < 2.0.0 ")
        assert len(ranges) == 2
        assert ranges[0] == VersionRange(">=", (1, 0, 0))
        assert ranges[1] == VersionRange("<", (2, 0, 0))

    def test_parse_invalid_requirements(self) -> None:
        """Test parsing invalid requirement strings."""
        with pytest.raises(ValueError, match="Empty version requirement"):
            parse_version_requirement("")

        with pytest.raises(ValueError, match="Invalid version range format"):
            parse_version_requirement("1.0.0")  # Missing operator

        with pytest.raises(ValueError, match="Invalid version range format"):
            parse_version_requirement("~1.0.0")  # Unsupported operator

        with pytest.raises(ValueError, match="Invalid version in range"):
            parse_version_requirement(">=1.0.a")  # Invalid version


class TestVersionCompatibilityChecking:
    """Tests for version compatibility checking."""

    def test_greater_than_equal_compatible(self) -> None:
        """Test >= operator compatibility checking."""
        # Compatible cases
        assert check_version_compatibility("1.0.0", ">=1.0.0") == (True, "")
        assert check_version_compatibility("1.1.0", ">=1.0.0") == (True, "")
        assert check_version_compatibility("2.0.0", ">=1.0.0") == (True, "")

        # Incompatible case
        is_compatible, error = check_version_compatibility("0.9.0", ">=1.0.0")
        assert not is_compatible
        assert "Requires version >= 1.0.0, got 0.9.0" in error

    def test_less_than_compatible(self) -> None:
        """Test < operator compatibility checking."""
        # Compatible cases
        assert check_version_compatibility("0.9.0", "<1.0.0") == (True, "")
        assert check_version_compatibility("0.8.7", "<1.0.0") == (True, "")

        # Incompatible case
        is_compatible, error = check_version_compatibility("1.0.0", "<1.0.0")
        assert not is_compatible
        assert "Requires version < 1.0.0, got 1.0.0" in error

    def test_range_compatible(self) -> None:
        """Test range compatibility checking."""
        # Compatible case
        assert check_version_compatibility("0.8.7", ">=0.8.0,<1.0.0") == (True, "")

        # Too low
        is_compatible, error = check_version_compatibility("0.7.0", ">=0.8.0,<1.0.0")
        assert not is_compatible
        assert "Requires version >= 0.8.0, got 0.7.0" in error

        # Too high
        is_compatible, error = check_version_compatibility("1.0.0", ">=0.8.0,<1.0.0")
        assert not is_compatible
        assert "Requires version < 1.0.0, got 1.0.0" in error

    def test_exact_version_compatible(self) -> None:
        """Test == operator compatibility checking."""
        # Compatible case
        assert check_version_compatibility("1.0.0", "==1.0.0") == (True, "")

        # Incompatible case
        is_compatible, error = check_version_compatibility("1.0.1", "==1.0.0")
        assert not is_compatible
        assert "Requires exact version 1.0.0, got 1.0.1" in error

    def test_not_equal_compatible(self) -> None:
        """Test != operator compatibility checking."""
        # Compatible case
        assert check_version_compatibility("1.0.1", "!=1.0.0") == (True, "")

        # Incompatible case
        is_compatible, error = check_version_compatibility("1.0.0", "!=1.0.0")
        assert not is_compatible
        assert "Incompatible with version 1.0.0, got 1.0.0" in error

    def test_complex_version_comparisons(self) -> None:
        """Test complex version number comparisons."""
        # Test different length versions
        assert check_version_compatibility("1.0", ">=1.0.0") == (True, "")
        assert check_version_compatibility("1.0.0", ">=1.0") == (True, "")

        # Test longer versions
        assert check_version_compatibility("1.2.3.4", ">=1.2.3") == (True, "")
        is_compatible, _ = check_version_compatibility("1.2.2.9", ">=1.2.3")
        assert not is_compatible

    def test_invalid_version_requirement(self) -> None:
        """Test handling of invalid version requirements."""
        is_compatible, error = check_version_compatibility("1.0.0", "invalid")
        assert not is_compatible
        assert "Invalid version requirement format" in error


class TestPluginCompatibilityIntegration:
    """Tests for plugin compatibility checking integration."""

    @patch("vibectl.version_compat.__version__", "0.9.0")
    def test_plugin_compatibility_current_version(self) -> None:
        """Test plugin compatibility with current vibectl version."""
        # This should be compatible with mocked version (0.9.0)
        is_compatible, error = check_plugin_compatibility(">=0.8.0,<1.0.0")
        assert is_compatible
        assert error == ""

    @patch("vibectl.version_compat.__version__", "0.9.0")
    def test_plugin_compatibility_future_version(self) -> None:
        """Test plugin compatibility with future version requirements."""
        # This should be incompatible with mocked version (0.9.0)
        is_compatible, error = check_plugin_compatibility(">=2.0.0,<3.0.0")
        assert not is_compatible
        assert "Requires version >= 2.0.0, got 0.9.0" in error

    @patch("vibectl.version_compat.__version__", "0.9.0")
    def test_plugin_compatibility_old_version(self) -> None:
        """Test plugin compatibility with old version requirements."""
        # This should be incompatible with mocked version (0.9.0)
        is_compatible, error = check_plugin_compatibility("<0.8.0")
        assert not is_compatible
        assert "Requires version < 0.8.0, got 0.9.0" in error

    @patch("vibectl.version_compat.__version__", "0.9.0")
    def test_plugin_compatibility_exact_match(self) -> None:
        """Test plugin compatibility with exact version match."""
        # Test exact match with mocked version
        is_compatible, error = check_plugin_compatibility("==0.9.0")
        assert is_compatible
        assert error == ""

        # Test exact match with different version
        is_compatible, error = check_plugin_compatibility("==0.8.6")
        assert not is_compatible
        assert "Requires exact version 0.8.6, got 0.9.0" in error
