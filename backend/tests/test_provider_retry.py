from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from decision_agent.shared.providers.retry import with_retry, _is_retryable
from decision_agent.shared.providers.registry import (
    FallbackProvider,
    _record_failure,
    _record_success,
    _circuit_is_open,
    _CIRCUIT_STATE,
    ProviderCircuitOpenError,
)
from decision_agent.shared.providers.mock import MockProvider


class TestWithRetry(unittest.TestCase):
    def test_success_on_first_attempt(self) -> None:
        calls = []
        def fn():
            calls.append(1)
            return "ok"
        result = with_retry(fn, max_attempts=3)
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 1)

    def test_retries_on_retryable_error_then_succeeds(self) -> None:
        calls = []
        class FakeRateLimitError(Exception):
            pass

        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise FakeRateLimitError("429 rate limit")
            return "ok"

        with patch("decision_agent.shared.providers.retry._is_retryable", return_value=True), \
             patch("decision_agent.shared.providers.retry.time") as mock_time:
            mock_time.sleep = MagicMock()
            result = with_retry(fn, max_attempts=4, base_delay=0.01)

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)

    def test_raises_on_non_retryable_error(self) -> None:
        calls = []
        def fn():
            calls.append(1)
            raise ValueError("not retryable")
        with self.assertRaises(ValueError):
            with_retry(fn, max_attempts=4)
        self.assertEqual(len(calls), 1)  # no retry on non-retryable

    def test_raises_after_max_attempts(self) -> None:
        calls = []
        class TransientError(Exception):
            pass

        def fn():
            calls.append(1)
            raise TransientError("503 unavailable")

        with patch("decision_agent.shared.providers.retry._is_retryable", return_value=True), \
             patch("decision_agent.shared.providers.retry.time") as mock_time:
            mock_time.sleep = MagicMock()
            with self.assertRaises(TransientError):
                with_retry(fn, max_attempts=3, base_delay=0.01)

        self.assertEqual(len(calls), 3)

    def test_on_retry_callback_called(self) -> None:
        retries_seen = []
        class FakeError(Exception):
            pass

        def fn():
            raise FakeError("429")

        with patch("decision_agent.shared.providers.retry._is_retryable", return_value=True), \
             patch("decision_agent.shared.providers.retry.time") as mock_time:
            mock_time.sleep = MagicMock()
            with self.assertRaises(FakeError):
                with_retry(fn, max_attempts=3, base_delay=0.01,
                           on_retry=lambda attempt, exc: retries_seen.append(attempt))

        self.assertEqual(retries_seen, [1, 2])


class TestIsRetryable(unittest.TestCase):
    def test_rate_limit_retryable(self) -> None:
        class RateLimitError(Exception): pass
        self.assertTrue(_is_retryable(RateLimitError("429")))

    def test_timeout_retryable(self) -> None:
        self.assertTrue(_is_retryable(TimeoutError("timed out")))

    def test_value_error_not_retryable(self) -> None:
        self.assertFalse(_is_retryable(ValueError("bad value")))

    def test_500_in_message_retryable(self) -> None:
        self.assertTrue(_is_retryable(RuntimeError("status 500 server error")))

    def test_connection_refused_not_retryable(self) -> None:
        import urllib.error
        exc = urllib.error.URLError("connection refused")
        self.assertFalse(_is_retryable(exc))


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self) -> None:
        _CIRCUIT_STATE.clear()

    def tearDown(self) -> None:
        _CIRCUIT_STATE.clear()

    def test_circuit_opens_after_threshold_failures(self) -> None:
        name = "test_provider_circuit"
        self.assertFalse(_circuit_is_open(name))
        for _ in range(3):
            _record_failure(name)
        self.assertTrue(_circuit_is_open(name))

    def test_success_resets_circuit(self) -> None:
        name = "test_provider_circuit2"
        for _ in range(3):
            _record_failure(name)
        self.assertTrue(_circuit_is_open(name))
        _record_success(name)
        self.assertFalse(_circuit_is_open(name))

    def test_circuit_recovers_after_reset_seconds(self) -> None:
        name = "test_provider_circuit3"
        for _ in range(3):
            _record_failure(name)
        self.assertTrue(_circuit_is_open(name))
        # Manually expire
        _CIRCUIT_STATE[name]["open_until"] = time.monotonic() - 1
        self.assertFalse(_circuit_is_open(name))


class TestFallbackProvider(unittest.TestCase):
    def setUp(self) -> None:
        _CIRCUIT_STATE.clear()

    def tearDown(self) -> None:
        _CIRCUIT_STATE.clear()

    def test_returns_primary_result_when_ok(self) -> None:
        primary = MockProvider()
        fallback = MockProvider()
        fp = FallbackProvider([primary, fallback])
        result = fp.complete("sys", "user")
        self.assertIsInstance(result, str)

    def test_falls_back_when_primary_fails(self) -> None:
        class FailingProvider:
            name = "failing"
            def complete(self, *a, **kw): raise RuntimeError("429")
            def complete_with_tools(self, *a, **kw): raise RuntimeError("429")

        primary = FailingProvider()
        fallback = MockProvider()
        fp = FallbackProvider([primary, fallback])  # type: ignore
        # Should not raise — falls back to mock
        result = fp.complete("sys", "user")
        self.assertIsInstance(result, str)

    def test_raises_when_all_providers_fail(self) -> None:
        class FailingProvider:
            name = "fail"
            def complete(self, *a, **kw): raise RuntimeError("down")
            def complete_with_tools(self, *a, **kw): raise RuntimeError("down")

        fp = FallbackProvider([FailingProvider(), FailingProvider()])  # type: ignore
        with self.assertRaises(RuntimeError):
            fp.complete("sys", "user")


if __name__ == "__main__":
    unittest.main()
