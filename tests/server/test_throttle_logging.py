"""Structured logging tests for throttle events."""

import json
import logging

import pytest

import vibectl.server.rate_limit_interceptor as rli


def test_log_throttle_event_formats_json(caplog: pytest.LogCaptureFixture) -> None:
    """Ensure _log_throttle_event emits a single-line JSON payload with keys."""

    caplog.set_level(logging.INFO, logger=rli.logger.name)

    rli._log_throttle_event(
        sub="demo-user",
        limit_type="rpm",
        current=10,
        allowed=5,
        path="/vibectl.v1.Foo/Bar",
    )

    # One record should have been produced
    records = [r for r in caplog.records if r.name == rli.logger.name]
    assert len(records) == 1

    payload = json.loads(records[0].msg)
    assert payload == {
        "sub": "demo-user",
        "limit_type": "rpm",
        "current": 10,
        "allowed": 5,
        "path": "/vibectl.v1.Foo/Bar",
    }
