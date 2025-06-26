"""Backend abstraction for rate-limit accounting.

Provides an in-process implementation suitable for single-process servers. The
interface is intentionally minimal so it can be swapped with a Redis or other
cluster-aware implementation later without touching interceptor logic.
"""

from collections import defaultdict
from threading import Lock
from time import time as _time
from typing import Final


class LimitBackend:
    """Abstract rate-limit backend."""

    def incr_fixed_window(self, key: str, window_s: int, amount: int = 1) -> int:
        """Increment *key* inside a fixed window and return the new counter value."""
        raise NotImplementedError

    def acquire_concurrency(self, key: str, limit: int) -> bool:
        """Try to increment concurrent counter. Returns ``True`` on success."""
        raise NotImplementedError

    def release_concurrency(self, key: str, amount: int = 1) -> None:
        """Decrement concurrent counter after request completion."""
        raise NotImplementedError


class InMemoryLimitBackend(LimitBackend):
    """Thread-safe in-process backend for rate limiting.

    Not suitable for multi-process deployments but fine for the initial MVP.
    """

    _rpm_counters: dict[str, tuple[int, float]]
    _conc_counters: dict[str, int]
    _lock: Final[Lock]

    def __init__(self) -> None:
        self._rpm_counters = {}
        self._conc_counters = defaultdict(int)
        self._lock = Lock()

    # -------------------------------------------------------------- RPM bucket

    def incr_fixed_window(self, key: str, window_s: int, amount: int = 1) -> int:
        now = _time()
        with self._lock:
            count, window_start = self._rpm_counters.get(key, (0, now))
            if now - window_start >= window_s:
                # New window
                count = 0
                window_start = now
            count += amount
            self._rpm_counters[key] = (count, window_start)
            return count

    # ------------------------------------------------------------ concurrency

    def acquire_concurrency(self, key: str, limit: int) -> bool:
        with self._lock:
            current = self._conc_counters[key]
            if current >= limit:
                return False
            self._conc_counters[key] = current + 1
            return True

    def release_concurrency(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._conc_counters[key] = max(0, self._conc_counters[key] - amount)
