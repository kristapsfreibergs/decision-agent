from __future__ import annotations

import random
import time
from typing import Any, Callable, TypeVar

_T = TypeVar("_T")

# HTTP status codes that are transient and safe to retry.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _is_retryable(exc: BaseException) -> bool:
    """Return True if the exception looks like a transient provider error."""
    msg = str(exc).lower()
    # anthropic SDK raises specific types; check by name to avoid hard import
    type_name = type(exc).__name__
    if "ratelimit" in type_name.lower():
        return True
    if "overload" in type_name.lower():
        return True
    if "internalserver" in type_name.lower():
        return True
    if "timeout" in type_name.lower() or "timed out" in msg:
        return True
    # urllib errors from Ollama
    if "urlerror" in type_name.lower():
        # Connection refused is not retryable — provider is down
        if "connection refused" in msg:
            return False
        return True
    # Generic HTTP status codes embedded in message
    for code in _RETRYABLE_STATUS:
        if str(code) in msg:
            return True
    return False


def with_retry(
    fn: Callable[[], _T],
    *,
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> _T:
    """Call fn() with exponential backoff + jitter on transient errors.

    Args:
        fn:           Zero-argument callable to invoke.
        max_attempts: Maximum total attempts (first call + retries).
        base_delay:   Initial wait in seconds before first retry.
        max_delay:    Cap on per-attempt wait.
        on_retry:     Optional callback(attempt_number, exc) for logging.

    Raises the last exception if all attempts are exhausted.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt == max_attempts or not _is_retryable(exc):
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            jitter = random.uniform(0, delay * 0.2)
            wait = delay + jitter
            if on_retry:
                on_retry(attempt, exc)
            time.sleep(wait)
    raise last_exc  # type: ignore[misc]
