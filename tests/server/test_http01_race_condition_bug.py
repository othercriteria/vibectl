"""
Test to reproduce the HTTP-01 challenge race condition bug.

This test reproduces the bug where challenge tokens are cleaned up
immediately after creation, before the ACME server can validate them.
"""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from vibectl.server.acme_client import ACMEClient
from vibectl.server.acme_manager import ACMEManager
from vibectl.server.http_challenge_server import HTTPChallengeServer


class TestHTTP01RaceConditionBug:
    """Test class to reproduce the HTTP-01 challenge race condition bug."""

    def test_acme_manager_race_condition_bug(self) -> None:
        """Test the ACTUAL race condition bug in ACMEManager._handle_http01_challenge().

        This reproduces the bug seen in production logs where:
        1. Challenge token is set in HTTPChallengeServer
        2. Challenge is submitted to ACME server
        3. **BUG**: Challenge token is immediately removed in finally block
        4. ACME server validation fails with 404

        The logs show:
        [DEBUG] Set challenge token: <token>
        [DEBUG] Removed challenge token: <token>  ← BUG: Immediate cleanup
        [WARNING] Challenge token not found: <token>
        """
        # Create mock HTTPChallengeServer
        mock_challenge_server = Mock(spec=HTTPChallengeServer)

        # Create ACMEManager with mock challenge server
        acme_config = {
            "email": "test@example.com",
            "domains": ["example.com"],
            "directory_url": "https://acme-staging-v02.api.letsencrypt.org/directory",
            "challenge": {"type": "http-01"},
        }

        manager = ACMEManager(
            challenge_server=mock_challenge_server, acme_config=acme_config
        )

        # Mock ACME client and challenge components
        mock_acme_client = Mock()
        mock_account_key = Mock()
        mock_acme_client._account_key = mock_account_key
        mock_acme_client._client = Mock()

        # Mock challenge details
        mock_challenge = Mock()
        mock_challenge.encode.return_value = "race_condition_token_123"
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            "validation_content",
        )

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_challenge

        # Track the order of operations
        operations = []

        def track_set_challenge(token: str, content: str) -> None:
            operations.append(f"SET_CHALLENGE: {token}")

        def track_remove_challenge(token: str) -> None:
            operations.append(f"REMOVE_CHALLENGE: {token}")

        def track_acme_submission(*args: Any, **kwargs: Any) -> Mock:
            operations.append("ACME_SUBMISSION")
            return Mock()

        # Set up tracking
        mock_challenge_server.set_challenge.side_effect = track_set_challenge
        mock_challenge_server.remove_challenge.side_effect = track_remove_challenge
        mock_acme_client._client.answer_challenge.side_effect = track_acme_submission

        # Execute the buggy method
        manager._handle_http01_challenge(
            challenge_body=mock_challenge_body,
            domain="example.com",
            challenge_dir=None,
            original_method=Mock(),
            acme_client=mock_acme_client,
        )

        # The token should remain available for ACME server validation
        expected_operations_without_race_condition = [
            "SET_CHALLENGE: race_condition_token_123",
            "ACME_SUBMISSION",
            # REMOVE_CHALLENGE should NOT happen here - it should happen later
            # after validation
        ]

        assert operations == expected_operations_without_race_condition, (
            f"FIXED: Challenge should remain after submission. Operations: {operations}"
        )

        # Verify the specific calls
        mock_challenge_server.set_challenge.assert_called_once_with(
            "race_condition_token_123", "validation_content"
        )
        mock_acme_client._client.answer_challenge.assert_called_once()

        # FIXED: Challenge should NOT be removed immediately after submission
        mock_challenge_server.remove_challenge.assert_not_called()

    def test_acme_manager_error_cleanup_behavior(self) -> None:
        """Test cleanup behavior when ACME submission fails.

        When submission fails, it's reasonable to clean up since the ACME server
        never received the challenge. This is different from the race condition
        where cleanup happens after successful submission."""
        # Create mock HTTPChallengeServer
        mock_challenge_server = Mock(spec=HTTPChallengeServer)

        # Create ACMEManager with mock challenge server
        acme_config = {
            "email": "test@example.com",
            "domains": ["example.com"],
            "directory_url": "https://acme-staging-v02.api.letsencrypt.org/directory",
            "challenge": {"type": "http-01"},
        }

        manager = ACMEManager(
            challenge_server=mock_challenge_server, acme_config=acme_config
        )

        # Mock ACME client that fails
        mock_acme_client = Mock()
        mock_account_key = Mock()
        mock_acme_client._account_key = mock_account_key
        mock_acme_client._client = Mock()
        mock_acme_client._client.answer_challenge.side_effect = Exception(
            "ACME submission failed"
        )

        # Mock challenge details
        mock_challenge = Mock()
        mock_challenge.encode.return_value = "error_token_456"
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            "error_validation",
        )

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_challenge

        # Track operations
        operations = []

        def track_set_challenge(token: str, content: str) -> None:
            operations.append(f"SET_CHALLENGE: {token}")

        def track_remove_challenge(token: str) -> None:
            operations.append(f"REMOVE_CHALLENGE: {token}")

        mock_challenge_server.set_challenge.side_effect = track_set_challenge
        mock_challenge_server.remove_challenge.side_effect = track_remove_challenge

        # Execute and expect failure
        with pytest.raises(Exception, match="ACME submission failed"):
            manager._handle_http01_challenge(
                challenge_body=mock_challenge_body,
                domain="error-test.com",
                challenge_dir=None,
                original_method=Mock(),
                acme_client=mock_acme_client,
            )

        # This is different from the race condition where cleanup happens
        # after successful submission
        expected_operations_with_error_cleanup = [
            "SET_CHALLENGE: error_token_456",
            "REMOVE_CHALLENGE: error_token_456",
            # OK: Cleanup on submission error is reasonable
        ]

        assert operations == expected_operations_with_error_cleanup, (
            f"Error cleanup behavior is acceptable. Operations: {operations}"
        )

        # Verify cleanup happened on error (this is acceptable behavior)
        mock_challenge_server.remove_challenge.assert_called_once_with(
            "error_token_456"
        )

    def test_http01_challenge_file_cleaned_up_before_validation(self) -> None:
        """Test that reproduces the race condition bug.

        The bug: HTTP-01 challenge files are cleaned up immediately after
        submission, before the ACME server has a chance to validate them.

        Expected behavior: Challenge files should remain until validation completes.
        Actual behavior: Challenge files are deleted in finally block immediately.
        """
        # Create a temporary directory for challenge files
        with tempfile.TemporaryDirectory() as temp_dir:
            challenge_dir = Path(temp_dir) / ".well-known" / "acme-challenge"

            # Create ACME client
            client = ACMEClient(email="test@example.com")

            # Mock the ACME client components
            mock_client = Mock()
            mock_account_key = Mock()

            # Set up the mock challenge
            mock_challenge = Mock()
            mock_challenge.encode.return_value = "test_token_123"
            mock_challenge.response_and_validation.return_value = (
                Mock(),
                "test_validation_content",
            )

            mock_challenge_body = Mock()
            mock_challenge_body.chall = mock_challenge

            # Set up mocks on client instance
            client._client = mock_client
            client._account_key = mock_account_key

            # Track the challenge file lifecycle
            challenge_files_during_submission: list[Path] = []
            challenge_files_after_submission: list[Path] = []

            def track_files_during_submission(*args: Any, **kwargs: Any) -> Mock:
                """Track which challenge files exist during submission."""
                # Check which challenge files exist right now
                if challenge_dir.exists():
                    challenge_files_during_submission.extend(
                        list(challenge_dir.glob("*"))
                    )
                # Call the original mock
                return Mock()

            # Set up the mock to track file state during submission
            mock_client.answer_challenge.side_effect = track_files_during_submission

            # Call the method that contains the race condition
            client._complete_http01_challenge(
                challenge_body=mock_challenge_body,
                domain="example.com",
                challenge_dir=str(challenge_dir),
            )

            # Check what files exist after the method completes
            if challenge_dir.exists():
                challenge_files_after_submission.extend(list(challenge_dir.glob("*")))

            assert len(challenge_files_during_submission) > 0, (
                "Challenge file should exist during ACME submission"
            )

            assert len(challenge_files_after_submission) > 0, (
                "Challenge file should remain after submission until validation done"
            )

            # The file should have been created temporarily
            mock_challenge.encode.assert_called_once_with("token")
            mock_challenge.response_and_validation.assert_called_once_with(
                mock_account_key
            )

            # Verify the file is tracked for later cleanup
            assert "example.com" in client._http01_challenge_files, (
                "Challenge file should be tracked for cleanup after validation"
            )

    def test_http01_challenge_race_condition_timeline(self) -> None:
        """Test the exact timeline that causes the race condition.

        This test demonstrates the problematic sequence:
        1. Create challenge file
        2. Submit challenge to ACME server
        3. **BUG**: Immediately clean up challenge file (in finally block)
        4. ACME server tries to validate → fails because file is gone
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            challenge_dir = Path(temp_dir) / ".well-known" / "acme-challenge"

            client = ACMEClient(email="test@example.com")

            # Mock components
            mock_client = Mock()
            mock_account_key = Mock()
            mock_challenge = Mock()

            # Configure mocks
            mock_challenge.encode.return_value = "race_condition_token"
            mock_challenge.response_and_validation.return_value = (
                Mock(),
                "validation_data",
            )

            mock_challenge_body = Mock()
            mock_challenge_body.chall = mock_challenge

            client._client = mock_client
            client._account_key = mock_account_key

            # Track the timeline of file operations
            timeline: list[str] = []

            def track_challenge_submission(*args: Any, **kwargs: Any) -> Mock:
                """Track when challenge is submitted and file state."""
                # Check if challenge file still exists when ACME server would access it
                token_file = challenge_dir / "race_condition_token"
                file_exists_during_submission = token_file.exists()
                timeline.append(
                    f"ACME submission - file exists: {file_exists_during_submission}"
                )
                return Mock()

            mock_client.answer_challenge.side_effect = track_challenge_submission

            # Execute the buggy method
            client._complete_http01_challenge(
                challenge_body=mock_challenge_body,
                domain="race-test.example.com",
                challenge_dir=str(challenge_dir),
            )

            # Check final file state
            token_file = challenge_dir / "race_condition_token"
            file_exists_after_completion = token_file.exists()
            timeline.append(
                f"After method completion - file exists: {file_exists_after_completion}"
            )

            # Verify the race condition timeline
            assert "ACME submission - file exists: True" in timeline, (
                "Challenge file should exist during ACME submission"
            )

            assert "After method completion - file exists: True" in timeline, (
                "FIXED: Challenge file should remain after submission until validation"
            )

            # This demonstrates the fix: the file is NOT cleaned up in the finally block
            # but remains available for ACME server validation

    @patch("vibectl.server.acme_client.Path")
    def test_http01_challenge_cleanup_timing_with_mocked_filesystem(
        self, mock_path_class: Mock
    ) -> None:
        """Test the race condition using mocked filesystem to prove the timing issue."""

        # Set up mock path and file operations
        mock_challenge_path = Mock()
        mock_challenge_file = Mock()
        mock_path_class.return_value = mock_challenge_path
        mock_challenge_path.mkdir = Mock()
        mock_challenge_path.__truediv__ = Mock(return_value=mock_challenge_file)

        # Track when write and unlink are called
        write_called = False
        unlink_called = False
        submission_called = False

        def mock_write_text(content: str) -> None:
            nonlocal write_called
            write_called = True

        def mock_unlink() -> None:
            nonlocal unlink_called, submission_called
            unlink_called = True
            # The fix: unlink should NOT be called before submission completes
            # This assertion should now pass with our fix

        def mock_submission(*args: Any, **kwargs: Any) -> Mock:
            nonlocal submission_called, unlink_called
            submission_called = True
            # The fix: file should NOT get unlinked immediately after this call
            assert not unlink_called, "FIXED: File should still exist during submission"
            return Mock()

        mock_challenge_file.write_text = mock_write_text
        mock_challenge_file.unlink = mock_unlink

        # Set up ACME client
        client = ACMEClient(email="test@example.com")
        client._client = Mock()
        client._client.answer_challenge.side_effect = mock_submission
        client._account_key = Mock()

        # Mock challenge components
        mock_challenge = Mock()
        mock_challenge.encode.return_value = "timing_test_token"
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            "test_validation",
        )

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_challenge

        # Execute the method - this should NOT trigger the race condition anymore
        client._complete_http01_challenge(
            challenge_body=mock_challenge_body,
            domain="timing-test.example.com",
            challenge_dir="/tmp/test",
        )

        # Verify the fix worked
        assert write_called, "Challenge file should have been written"
        assert submission_called, "Challenge should have been submitted"
        assert not unlink_called, (
            "FIXED: Challenge file should NOT be cleaned up immediately"
        )

        # The fix means unlink does NOT happen immediately after submission,
        # but only after validation completes (which we're not testing here)
