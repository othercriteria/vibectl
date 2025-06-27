"""Tests for prometheus metrics integration."""

from unittest.mock import patch

from vibectl.server import metrics as m


def test_init_metrics_server_idempotent() -> None:
    """Calling init_metrics_server twice should invoke prometheus only once."""

    with patch("vibectl.server.metrics.start_http_server") as mock_start:
        m.init_metrics_server(port=12345)
        m.init_metrics_server(port=12345)

        # start_http_server should be called exactly once with our port
        mock_start.assert_called_once_with(12345)
