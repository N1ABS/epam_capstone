"""
Sliding-window rate limiter for per-user request throttling.

Defaults (configurable via environment variables):
    RATE_LIMIT_MAX_REQUESTS   = 10   (max requests per rolling window)
    RATE_LIMIT_WINDOW_SECONDS = 60   (window size in seconds)

Thread-safe: a module-level lock protects the shared request log.
"""
import logging
import threading
import time
from collections import defaultdict, deque

from src.config import RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS

logger = logging.getLogger(__name__)

_lock = threading.Lock()
# Maps user_id → deque of request timestamps (float, UTC seconds)
_request_log: dict[str, deque] = defaultdict(deque)


class RateLimitExceededError(Exception):
    """Raised when a user exceeds the configured request rate."""


def check_rate_limit(user_id: str) -> None:
    """
    Enforce the sliding-window rate limit for *user_id*.

    Records the current request and evicts timestamps that have fallen
    outside the rolling window. Raises RateLimitExceededError when the
    caller has already exhausted their quota for the current window.

    Args:
        user_id: Opaque identifier for the caller (e.g. thread_id, IP).

    Raises:
        RateLimitExceededError: When the rate limit is exceeded.
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    with _lock:
        timestamps = _request_log[user_id]

        # Evict timestamps that have fallen outside the current window.
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
            oldest = timestamps[0]
            retry_after = max(1, int(RATE_LIMIT_WINDOW_SECONDS - (now - oldest)) + 1)
            logger.warning(
                "[RateLimiter] user='%s' exceeded limit (%d/%d). retry_after=%ds",
                user_id,
                len(timestamps),
                RATE_LIMIT_MAX_REQUESTS,
                retry_after,
            )
            raise RateLimitExceededError(
                f"Rate limit exceeded ({RATE_LIMIT_MAX_REQUESTS} requests / "
                f"{RATE_LIMIT_WINDOW_SECONDS}s). "
                f"Please wait {retry_after} second(s) before retrying."
            )

        timestamps.append(now)
        logger.debug(
            "[RateLimiter] user='%s' request %d/%d accepted",
            user_id,
            len(timestamps),
            RATE_LIMIT_MAX_REQUESTS,
        )


def reset_limits(user_id: str | None = None) -> None:
    """
    Clear recorded request timestamps.

    If *user_id* is given, only that user's window is cleared.
    If *user_id* is None, all users' windows are cleared.

    Intended for use in tests only — not part of the production API.
    """
    with _lock:
        if user_id is not None:
            _request_log.pop(user_id, None)
        else:
            _request_log.clear()
