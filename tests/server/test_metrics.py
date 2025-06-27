"""Tests for prometheus metrics integration."""

from unittest.mock import patch

import pytest

from vibectl.server import metrics as m
from vibectl.server.main import _maybe_start_metrics


def test_init_metrics_server_idempotent() -> None:
    """Calling init_metrics_server twice should invoke prometheus only once."""

    with patch("vibectl.server.metrics.start_http_server") as mock_start:
        m.init_metrics_server(port=12345)
        m.init_metrics_server(port=12345)

        # start_http_server should be called exactly once with our port
        mock_start.assert_called_once_with(12345)


@pytest.mark.parametrize("enabled,expected_calls", [(True, 1), (False, 0)])
def test_maybe_start_metrics(enabled: bool, expected_calls: int) -> None:
    """_maybe_start_metrics should conditionally start the exporter."""

    opts = {"enable_metrics": enabled, "metrics_port": 9100}

    # Patch inside vibectl.server.metrics where the helper imports from
    import vibectl.server.metrics as metrics_mod

    # Ensure fresh state for each parameterisation
    metrics_mod._METRICS_STARTED = False

    with patch("vibectl.server.metrics.start_http_server") as mock_start:
        _maybe_start_metrics(opts)
        assert mock_start.call_count == expected_calls
