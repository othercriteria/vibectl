"""
Tests for the audit logging functionality.

This module provides comprehensive tests for the AuditLogger class,
including structured logging, secret detection events, and proxy connections.
"""

import json
import tempfile
from datetime import UTC, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from vibectl.security.audit import AuditLogger
from vibectl.security.config import ConfirmationMode, SecurityConfig
from vibectl.security.sanitizer import DetectedSecret


class TestAuditLogger:
    """Test the AuditLogger class functionality."""

    @pytest.fixture
    def security_config(self) -> SecurityConfig:
        """Create a SecurityConfig for testing."""
        return SecurityConfig(
            sanitize_requests=True,
            audit_logging=True,
            audit_log_path="/tmp/test_audit.log",
            confirmation_mode=ConfirmationMode.PER_COMMAND,
            warn_sanitization=True,
        )

    @pytest.fixture
    def security_config_disabled(self) -> SecurityConfig:
        """Create a SecurityConfig with audit logging disabled."""
        return SecurityConfig(
            sanitize_requests=True,
            audit_logging=False,
            audit_log_path=None,
            confirmation_mode=ConfirmationMode.PER_COMMAND,
            warn_sanitization=True,
        )

    @pytest.fixture
    def detected_secrets(self) -> list[DetectedSecret]:
        """Create sample detected secrets for testing."""
        return [
            DetectedSecret(
                secret_type="k8s-token",
                start_pos=10,
                end_pos=50,
                original_text="eyJhbGciOiJSUzI1NiIsImtpZCI6IjEyMyJ9.eyJpc3MiOiJrOHMtc2VydmljZWFjY291bnQifQ.signature",
                confidence=0.9,
            ),
            DetectedSecret(
                secret_type="base64-data",
                start_pos=60,
                end_pos=100,
                original_text="aGVsbG8gd29ybGQgc2VjcmV0IGRhdGEgdGVzdA==",
                confidence=0.8,
            ),
        ]

    def test_audit_logger_initialization_enabled(
        self, security_config: SecurityConfig
    ) -> None:
        """Test AuditLogger initialization when audit logging is enabled."""
        logger = AuditLogger(security_config, proxy_profile="test-profile")

        assert logger.enabled is True
        assert logger.proxy_profile == "test-profile"
        assert logger.log_path == Path("/tmp/test_audit.log")

    def test_audit_logger_initialization_disabled(
        self, security_config_disabled: SecurityConfig
    ) -> None:
        """Test AuditLogger initialization when audit logging is disabled."""
        logger = AuditLogger(security_config_disabled)

        assert logger.enabled is False
        assert logger.proxy_profile is None
        assert logger.log_path is None

    def test_audit_logger_initialization_default_path(self) -> None:
        """Test AuditLogger initialization with default audit log path."""
        config = SecurityConfig(
            sanitize_requests=True,
            audit_logging=True,
            audit_log_path=None,  # Should use default
            confirmation_mode=ConfirmationMode.PER_COMMAND,
            warn_sanitization=True,
        )

        with patch("vibectl.security.audit.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp/testuser")  # Use /tmp instead of /home
            logger = AuditLogger(config, proxy_profile="test-profile")

            expected_path = Path("/tmp/testuser/.config/vibectl/audit-test-profile.log")
            assert logger.log_path == expected_path

    def test_hash_content(self, security_config: SecurityConfig) -> None:
        """Test content hashing."""
        logger = AuditLogger(security_config)

        content = "kubectl get pods --namespace production"
        hash_result = logger._hash_content(content)

        # Should return a hex hash (no "sha256:" prefix in the implementation)
        assert len(hash_result) == 64  # SHA256 hex length
        assert hash_result != "null"

        # Same content should produce same hash
        hash_result2 = logger._hash_content(content)
        assert hash_result == hash_result2

        # Different content should produce different hash
        different_content = "kubectl get nodes"
        different_hash = logger._hash_content(different_content)
        assert different_hash != hash_result

    def test_hash_content_empty_content(self, security_config: SecurityConfig) -> None:
        """Test content hashing with empty and None content."""
        logger = AuditLogger(security_config)

        # Empty string returns "null"
        hash_result = logger._hash_content("")
        assert hash_result == "null"

        # None content also returns "null"
        null_hash = logger._hash_content(None)
        assert null_hash == "null"

    def test_write_audit_entry_disabled(
        self, security_config_disabled: SecurityConfig
    ) -> None:
        """Test that audit logging is skipped when disabled."""
        logger = AuditLogger(security_config_disabled)

        # Should not raise an exception, just return early
        logger._write_audit_entry({"test": "data"})

    def test_write_audit_entry_enabled(self, security_config: SecurityConfig) -> None:
        """Test writing audit log entries when enabled."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            # Override the log path for testing
            logger = AuditLogger(security_config)
            logger.log_path = temp_path

            test_data = {
                "timestamp": "2024-01-15T10:30:45Z",
                "event_type": "test_event",
                "test_field": "test_value",
            }

            logger._write_audit_entry(test_data)

            # Verify the log was written
            with open(temp_path) as f:
                log_content = f.read().strip()

            # Should be valid JSON
            parsed_log = json.loads(log_content)
            assert parsed_log == test_data

        finally:
            temp_path.unlink(missing_ok=True)

    def test_write_audit_entry_creates_directory(
        self, security_config: SecurityConfig
    ) -> None:
        """Test that audit logging creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a nested path that doesn't exist
            nested_path = Path(temp_dir) / "nested" / "audit" / "test.log"

            # Set the audit log path in config so __init__ creates the directory
            security_config.audit_log_path = str(nested_path)
            logger = AuditLogger(security_config)

            test_data = {"test": "data"}
            logger._write_audit_entry(test_data)

            # Verify the directory was created and file was written
            assert nested_path.exists()
            assert nested_path.parent.exists()

            with open(nested_path) as f:
                parsed_log = json.loads(f.read().strip())
                assert parsed_log == test_data

    @patch("vibectl.security.audit.logger")
    def test_write_audit_entry_error_handling(
        self, mock_logger: Mock, security_config: SecurityConfig
    ) -> None:
        """Test error handling when writing audit log fails."""
        # Use a path that will cause permission error
        logger = AuditLogger(security_config)
        logger.log_path = Path("/root/forbidden/audit.log")

        test_data = {"test": "data"}

        # Should not raise exception, but should log error
        logger._write_audit_entry(test_data)

        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        assert "Failed to write audit log entry" in error_call

    def test_log_llm_request_disabled(
        self, security_config_disabled: SecurityConfig
    ) -> None:
        """Test LLM request logging when audit logging is disabled."""
        logger = AuditLogger(security_config_disabled)

        # Should not raise an exception
        logger.log_llm_request(
            request_id="test-123",
            request_content="test request",
            response_content="test response",
            secrets_detected=[],
            model_used="test-model",
        )

    def test_log_llm_request_enabled(
        self, security_config: SecurityConfig, detected_secrets: list[DetectedSecret]
    ) -> None:
        """Test LLM request logging when enabled."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            logger = AuditLogger(security_config, proxy_profile="test-profile")
            logger.log_path = temp_path

            with patch("vibectl.security.audit.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime(
                    2024, 1, 15, 10, 30, 45, tzinfo=UTC
                )
                mock_datetime.timezone = timezone

                logger.log_llm_request(
                    request_id="test-request-123",
                    request_content="kubectl get pods --namespace production",
                    response_content="pod1  Running\npod2  Pending",
                    secrets_detected=detected_secrets,
                    model_used="claude-3-sonnet",
                    command_generated="kubectl get pods -n production",
                    user_approved=True,
                    additional_metadata={"custom_field": "custom_value"},
                )

            # Verify the log entry
            with open(temp_path) as f:
                log_entry = json.loads(f.read().strip())

            assert log_entry["timestamp"] == "2024-01-15T10:30:45+00:00"
            assert log_entry["proxy_profile"] == "test-profile"
            assert log_entry["request_id"] == "test-request-123"
            assert log_entry["event_type"] == "llm_request"
            assert log_entry["model_used"] == "claude-3-sonnet"
            assert log_entry["command_generated"] == "kubectl get pods -n production"
            assert log_entry["user_approved"] is True
            assert log_entry["secrets_detected"] == 2
            assert log_entry["secrets_types"] == ["k8s-token", "base64-data"]
            assert log_entry["custom_field"] == "custom_value"

            # Check that hashes are present and properly formatted
            assert "request_hash" in log_entry
            assert len(log_entry["request_hash"]) == 64  # SHA256 hex length
            assert "response_hash" in log_entry
            assert len(log_entry["response_hash"]) == 64

        finally:
            temp_path.unlink(missing_ok=True)

    def test_log_llm_request_no_secrets(self, security_config: SecurityConfig) -> None:
        """Test LLM request logging with no detected secrets."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            logger = AuditLogger(security_config)
            logger.log_path = temp_path

            logger.log_llm_request(
                request_id="test-request-456",
                request_content="kubectl get nodes",
                response_content="node1  Ready\nnode2  Ready",
                secrets_detected=[],
                model_used="gpt-4",
            )

            with open(temp_path) as f:
                log_entry = json.loads(f.read().strip())

            assert log_entry["secrets_detected"] == 0
            assert log_entry["secrets_types"] == []

        finally:
            temp_path.unlink(missing_ok=True)

    def test_log_sanitization_event_disabled(
        self, security_config_disabled: SecurityConfig
    ) -> None:
        """Test sanitization event logging when audit logging is disabled."""
        logger = AuditLogger(security_config_disabled)

        # Should not raise an exception
        logger.log_sanitization_event(
            request_id="test-123",
            secrets_detected=[],
            original_content="original content",
            sanitized_content="sanitized content",
        )

    def test_log_sanitization_event_enabled(
        self, security_config: SecurityConfig, detected_secrets: list[DetectedSecret]
    ) -> None:
        """Test sanitization event logging when enabled."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            logger = AuditLogger(security_config, proxy_profile="sanitization-profile")
            logger.log_path = temp_path

            with patch("vibectl.security.audit.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime(
                    2024, 1, 15, 14, 45, 30, tzinfo=UTC
                )
                mock_datetime.timezone = timezone

                logger.log_sanitization_event(
                    request_id="sanitization-123",
                    secrets_detected=detected_secrets,
                    original_content="original content with secret",
                    sanitized_content="sanitized content with [REDACTED]",
                )

            # Verify the log entry
            with open(temp_path) as f:
                log_entry = json.loads(f.read().strip())

            assert log_entry["timestamp"] == "2024-01-15T14:45:30+00:00"
            assert log_entry["proxy_profile"] == "sanitization-profile"
            assert log_entry["request_id"] == "sanitization-123"
            assert log_entry["event_type"] == "sanitization"
            assert log_entry["secrets_detected"] == 2
            assert log_entry["secrets_types"] == ["k8s-token", "base64-data"]

            # Should have content hashes
            assert "original_hash" in log_entry
            assert "sanitized_hash" in log_entry
            assert len(log_entry["original_hash"]) == 64
            assert len(log_entry["sanitized_hash"]) == 64

        finally:
            temp_path.unlink(missing_ok=True)

    def test_log_proxy_connection_disabled(
        self, security_config_disabled: SecurityConfig
    ) -> None:
        """Test proxy connection logging when audit logging is disabled."""
        logger = AuditLogger(security_config_disabled)

        # Should not raise an exception
        logger.log_proxy_connection(
            server_url="vibectl-server://test.example.com:443",
            success=True,
        )

    def test_log_proxy_connection_enabled(
        self, security_config: SecurityConfig
    ) -> None:
        """Test proxy connection logging when enabled."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            logger = AuditLogger(security_config, proxy_profile="connection-profile")
            logger.log_path = temp_path

            with patch("vibectl.security.audit.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime(
                    2024, 1, 15, 16, 20, 15, tzinfo=UTC
                )
                mock_datetime.timezone = timezone

                logger.log_proxy_connection(
                    server_url="vibectl-server://test.example.com:443",
                    success=True,
                    connection_time_ms=125.5,
                )

            # Verify the log entry
            with open(temp_path) as f:
                log_entry = json.loads(f.read().strip())

            assert log_entry["timestamp"] == "2024-01-15T16:20:15+00:00"
            assert log_entry["proxy_profile"] == "connection-profile"
            assert log_entry["event_type"] == "proxy_connection"
            assert log_entry["server_url"] == "vibectl-server://test.example.com:443"
            assert log_entry["success"] is True
            assert log_entry["connection_time_ms"] == 125.5
            assert "request_id" in log_entry  # Should generate UUID
            assert "error_message" in log_entry
            assert log_entry["error_message"] is None

        finally:
            temp_path.unlink(missing_ok=True)

    def test_log_proxy_connection_error(self, security_config: SecurityConfig) -> None:
        """Test proxy connection logging with error."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            logger = AuditLogger(security_config)
            logger.log_path = temp_path

            logger.log_proxy_connection(
                server_url="vibectl-server://invalid.example.com:443",
                success=False,
                error_message="Connection timeout",
            )

            with open(temp_path) as f:
                log_entry = json.loads(f.read().strip())

            assert log_entry["success"] is False
            assert log_entry["error_message"] == "Connection timeout"
            assert log_entry["connection_time_ms"] is None

        finally:
            temp_path.unlink(missing_ok=True)

    def test_get_audit_entries_no_file(self, security_config: SecurityConfig) -> None:
        """Test getting audit entries when no log file exists."""
        logger = AuditLogger(security_config)
        logger.log_path = Path("/tmp/nonexistent_audit.log")

        entries = logger.get_audit_entries()
        assert entries == []

    def test_get_audit_entries_with_data(self, security_config: SecurityConfig) -> None:
        """Test getting audit entries from existing log file."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            logger = AuditLogger(security_config)
            logger.log_path = temp_path

            # Log multiple entries
            logger.log_llm_request(
                request_id="test-1",
                request_content="request 1",
                response_content="response 1",
                secrets_detected=[],
                model_used="model-1",
            )
            logger.log_proxy_connection(
                server_url="vibectl-server://test.example.com",
                success=True,
            )

            # Read entries back
            entries = logger.get_audit_entries()

            assert len(entries) == 2
            assert entries[0]["event_type"] == "llm_request"
            assert entries[0]["request_id"] == "test-1"
            assert entries[1]["event_type"] == "proxy_connection"
            assert entries[1]["success"] is True

        finally:
            temp_path.unlink(missing_ok=True)

    def test_get_audit_entries_with_filters(
        self, security_config: SecurityConfig
    ) -> None:
        """Test getting audit entries with filters applied."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            logger = AuditLogger(security_config)
            logger.log_path = temp_path

            # Log entries of different types
            logger.log_llm_request(
                request_id="llm-1",
                request_content="request",
                response_content="response",
                secrets_detected=[],
                model_used="model",
            )
            logger.log_proxy_connection(
                server_url="vibectl-server://test.example.com",
                success=True,
            )
            logger.log_sanitization_event(
                request_id="sanitize-1",
                secrets_detected=[],
                original_content="original",
                sanitized_content="sanitized",
            )

            # Filter by event type
            llm_entries = logger.get_audit_entries(event_type="llm_request")
            assert len(llm_entries) == 1
            assert llm_entries[0]["request_id"] == "llm-1"

            connection_entries = logger.get_audit_entries(event_type="proxy_connection")
            assert len(connection_entries) == 1
            assert connection_entries[0]["success"] is True

            # Test limit
            limited_entries = logger.get_audit_entries(limit=2)
            assert len(limited_entries) == 2

        finally:
            temp_path.unlink(missing_ok=True)

    def test_unicode_content_handling(self, security_config: SecurityConfig) -> None:
        """Test that the audit logger handles Unicode content properly."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            logger = AuditLogger(security_config)
            logger.log_path = temp_path

            # Test with Unicode content
            unicode_content = "kubectl get pods 🚀 --namespace=测试"
            unicode_response = "pod-测试 Running ✅"

            logger.log_llm_request(
                request_id="unicode-test",
                request_content=unicode_content,
                response_content=unicode_response,
                secrets_detected=[],
                model_used="test-model",
            )

            # Verify the log was written correctly
            with open(temp_path, encoding="utf-8") as f:
                log_entry = json.loads(f.read().strip())

            # Hashes should be generated correctly for Unicode content
            assert "request_hash" in log_entry
            assert "response_hash" in log_entry
            assert len(log_entry["request_hash"]) == 64
            assert len(log_entry["response_hash"]) == 64

        finally:
            temp_path.unlink(missing_ok=True)

    def test_large_content_handling(self, security_config: SecurityConfig) -> None:
        """Test that the audit logger handles large content efficiently."""
        logger = AuditLogger(security_config)

        # Test with large content (1MB)
        large_content = "x" * (1024 * 1024)

        # Should not raise an exception and should generate hash efficiently
        hash_result = logger._hash_content(large_content)
        assert len(hash_result) == 64
        assert hash_result != "null"

    def test_multiple_log_entries(self, security_config: SecurityConfig) -> None:
        """Test writing multiple log entries to the same file."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            logger = AuditLogger(security_config)
            logger.log_path = temp_path

            # Log multiple entries
            logger.log_llm_request("test-1", "request 1", "response 1", [], "model-1")
            logger.log_proxy_connection("vibectl-server://test.example.com", True)
            logger.log_sanitization_event("sanitize-1", [], "original", "sanitized")

            # Verify all entries were written
            with open(temp_path) as f:
                lines = f.read().strip().split("\n")

            assert len(lines) == 3

            # Each line should be valid JSON
            for line in lines:
                log_entry = json.loads(line)
                assert "timestamp" in log_entry
                assert "event_type" in log_entry

            # Verify specific entries
            entry1 = json.loads(lines[0])
            assert entry1["event_type"] == "llm_request"
            assert entry1["request_id"] == "test-1"

            entry2 = json.loads(lines[1])
            assert entry2["event_type"] == "proxy_connection"
            assert entry2["success"] is True

            entry3 = json.loads(lines[2])
            assert entry3["event_type"] == "sanitization"
            assert entry3["request_id"] == "sanitize-1"

        finally:
            temp_path.unlink(missing_ok=True)
