import time

from vibectl.server.limit_backend import InMemoryLimitBackend


def test_fixed_window_resets() -> None:
    backend = InMemoryLimitBackend()
    key = "test:rpm"

    assert backend.incr_fixed_window(key, 1) == 1
    assert backend.incr_fixed_window(key, 1) == 2

    # Wait for window rollover
    time.sleep(1.1)
    assert backend.incr_fixed_window(key, 1) == 1  # Counter reset


def test_concurrency_acquire_release() -> None:
    backend = InMemoryLimitBackend()
    key = "user:conc"

    assert backend.acquire_concurrency(key, limit=2) is True
    assert backend.acquire_concurrency(key, limit=2) is True
    assert backend.acquire_concurrency(key, limit=2) is False  # limit reached

    backend.release_concurrency(key)
    assert backend.acquire_concurrency(key, limit=2) is True
