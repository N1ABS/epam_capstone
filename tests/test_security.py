"""
Tests for security modules: rate limiter, PII detector, and authentication.

Positive scenarios:
  - Requests within the rate limit are accepted.
  - PII-free text passes through unchanged.
  - Correct credentials return True.

Negative scenarios:
  - Exceeding the rate limit raises RateLimitExceededError.
  - Email, phone, SSN, and IP addresses are detected and masked.
  - Wrong password or username returns False.
  - Empty credentials are rejected immediately.
"""
import time
from unittest.mock import patch

import pytest

from src.security.auth import generate_session_token, is_auth_enabled, verify_credentials
from src.security.pii_detector import PIIResult, detect_and_anonymise
from src.security.rate_limiter import (
    RateLimitExceededError,
    check_rate_limit,
    reset_limits,
)


# ══════════════════════════════════════════════════════════════════════════════
# Rate Limiter
# ══════════════════════════════════════════════════════════════════════════════


class TestRateLimiterPositive:
    def test_single_request_passes(self):
        user = "rl_single"
        reset_limits(user)
        check_rate_limit(user)  # must not raise

    def test_requests_within_limit_all_pass(self):
        """All requests up to the configured max must succeed."""
        from src.config import RATE_LIMIT_MAX_REQUESTS

        user = "rl_within_limit"
        reset_limits(user)
        for _ in range(RATE_LIMIT_MAX_REQUESTS):
            check_rate_limit(user)  # must not raise

    def test_different_users_have_independent_limits(self):
        """Exhausting one user's limit must not affect another user."""
        from src.config import RATE_LIMIT_MAX_REQUESTS

        user_a = "rl_user_a"
        user_b = "rl_user_b"
        reset_limits(user_a)
        reset_limits(user_b)

        # Exhaust user_a
        for _ in range(RATE_LIMIT_MAX_REQUESTS):
            check_rate_limit(user_a)

        # user_b must still be unaffected
        check_rate_limit(user_b)  # must not raise

    def test_window_resets_after_expiry(self):
        """After the window expires, a previously throttled user can request again."""
        from src.config import RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS

        user = "rl_window_reset"
        reset_limits(user)

        with patch("src.security.rate_limiter.time") as mock_time:
            # All requests arrive at t=0
            mock_time.time.return_value = 0.0
            for _ in range(RATE_LIMIT_MAX_REQUESTS):
                check_rate_limit(user)

            # Advance past the full window — all previous timestamps expire
            mock_time.time.return_value = float(RATE_LIMIT_WINDOW_SECONDS + 1)
            check_rate_limit(user)  # must not raise


class TestRateLimiterNegative:
    def test_exceeds_limit_raises(self):
        """One request beyond the limit must raise RateLimitExceededError."""
        from src.config import RATE_LIMIT_MAX_REQUESTS

        user = "rl_exceed"
        reset_limits(user)
        for _ in range(RATE_LIMIT_MAX_REQUESTS):
            check_rate_limit(user)

        with pytest.raises(RateLimitExceededError, match="Rate limit exceeded"):
            check_rate_limit(user)

    def test_error_message_includes_retry_after(self):
        """The error message must tell the caller when to retry."""
        from src.config import RATE_LIMIT_MAX_REQUESTS

        user = "rl_message"
        reset_limits(user)
        for _ in range(RATE_LIMIT_MAX_REQUESTS):
            check_rate_limit(user)

        with pytest.raises(RateLimitExceededError) as exc_info:
            check_rate_limit(user)

        assert "second" in str(exc_info.value).lower()

    def test_burst_of_excess_requests_all_rejected(self):
        """Every request beyond the limit must be rejected, not just the first."""
        from src.config import RATE_LIMIT_MAX_REQUESTS

        user = "rl_burst"
        reset_limits(user)
        for _ in range(RATE_LIMIT_MAX_REQUESTS):
            check_rate_limit(user)

        for _ in range(3):
            with pytest.raises(RateLimitExceededError):
                check_rate_limit(user)

    def test_limit_not_reset_within_window(self):
        """A second call immediately after the first excess must still be rejected."""
        from src.config import RATE_LIMIT_MAX_REQUESTS

        user = "rl_no_early_reset"
        reset_limits(user)
        for _ in range(RATE_LIMIT_MAX_REQUESTS):
            check_rate_limit(user)

        with patch("src.security.rate_limiter.time") as mock_time:
            # Only 1 second has passed — window has not expired
            mock_time.time.return_value = 1.0
            with pytest.raises(RateLimitExceededError):
                check_rate_limit(user)


# ══════════════════════════════════════════════════════════════════════════════
# PII Detector
# ══════════════════════════════════════════════════════════════════════════════


class TestPIIDetectorPositive:
    def test_no_pii_returns_text_unchanged(self):
        text = "What is machine learning?"
        result = detect_and_anonymise(text)
        assert result.sanitised == text
        assert result.has_pii is False
        assert result.detections == []

    def test_original_always_preserved(self):
        """The original field must never be modified."""
        text = "Contact john@example.com for details"
        result = detect_and_anonymise(text)
        assert result.original == text

    def test_technical_text_no_false_positives(self):
        """Common technical text must not be flagged as PII."""
        text = "The API returns a 200 status code with JSON payload."
        result = detect_and_anonymise(text)
        assert result.has_pii is False

    def test_empty_string_handled_gracefully(self):
        result = detect_and_anonymise("")
        assert result.sanitised == ""
        assert result.has_pii is False

    def test_returns_pii_result_type(self):
        result = detect_and_anonymise("hello")
        assert isinstance(result, PIIResult)


class TestPIIDetectorNegative:
    def test_email_detected_and_masked(self):
        text = "Email me at john.doe@example.com for the report."
        result = detect_and_anonymise(text)
        assert "[EMAIL]" in result.sanitised
        assert "john.doe@example.com" not in result.sanitised
        assert "EMAIL" in result.detections

    def test_multiple_emails_all_masked(self):
        text = "CC alice@a.com and bob@b.org on this thread."
        result = detect_and_anonymise(text)
        assert result.sanitised.count("[EMAIL]") == 2
        assert result.detections.count("EMAIL") == 2

    def test_phone_number_detected_and_masked(self):
        text = "Call me at 555-867-5309 any time."
        result = detect_and_anonymise(text)
        assert "[PHONE]" in result.sanitised
        assert "555-867-5309" not in result.sanitised
        assert "PHONE" in result.detections

    def test_phone_with_country_code_detected(self):
        text = "International line: +1-800-555-0199"
        result = detect_and_anonymise(text)
        assert "[PHONE]" in result.sanitised
        assert "PHONE" in result.detections

    def test_ssn_detected_and_masked(self):
        text = "Social security number: 123-45-6789"
        result = detect_and_anonymise(text)
        assert "[SSN]" in result.sanitised
        assert "123-45-6789" not in result.sanitised
        assert "SSN" in result.detections

    def test_ip_address_detected_and_masked(self):
        text = "Server is running at 192.168.1.100"
        result = detect_and_anonymise(text)
        assert "[IP]" in result.sanitised
        assert "192.168.1.100" not in result.sanitised
        assert "IP" in result.detections

    def test_multiple_pii_types_all_masked(self):
        text = "Call 555-123-4567 or email user@example.com from server 10.0.0.1"
        result = detect_and_anonymise(text)
        assert result.has_pii is True
        assert "PHONE" in result.detections
        assert "EMAIL" in result.detections
        assert "IP" in result.detections
        assert "555-123-4567" not in result.sanitised
        assert "user@example.com" not in result.sanitised
        assert "10.0.0.1" not in result.sanitised

    def test_has_pii_flag_true_when_pii_found(self):
        result = detect_and_anonymise("admin@corp.com")
        assert result.has_pii is True

    def test_has_pii_flag_false_when_no_pii(self):
        result = detect_and_anonymise("What are neural networks?")
        assert result.has_pii is False


# ══════════════════════════════════════════════════════════════════════════════
# Authentication
# ══════════════════════════════════════════════════════════════════════════════


class TestAuthPositive:
    def test_correct_credentials_return_true(self):
        """Default credentials (admin / changeme) must be accepted."""
        # The default AUTH_PASSWORD_HASH is SHA-256("changeme")
        assert verify_credentials("admin", "changeme") is True

    def test_generate_session_token_returns_string(self):
        token = generate_session_token()
        assert isinstance(token, str)
        assert len(token) == 64  # 32 bytes → 64 hex chars

    def test_session_tokens_are_unique(self):
        """Each call must produce a distinct token."""
        tokens = {generate_session_token() for _ in range(10)}
        assert len(tokens) == 10

    def test_is_auth_enabled_returns_bool(self):
        result = is_auth_enabled()
        assert isinstance(result, bool)

    def test_auth_disabled_by_default(self):
        """When AUTH_ENABLED env var is absent, auth must be disabled."""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=False):
            # Reload module to pick up env without AUTH_ENABLED
            import importlib

            import src.security.auth as auth_module
            importlib.reload(auth_module)
            # Default is "false" so auth should be disabled
            assert auth_module._AUTH_ENABLED is False


class TestAuthNegative:
    def test_wrong_password_returns_false(self):
        assert verify_credentials("admin", "wrongpassword") is False

    def test_wrong_username_returns_false(self):
        assert verify_credentials("hacker", "changeme") is False

    def test_both_wrong_returns_false(self):
        assert verify_credentials("hacker", "wrongpassword") is False

    def test_empty_password_returns_false(self):
        assert verify_credentials("admin", "") is False

    def test_empty_username_returns_false(self):
        assert verify_credentials("", "changeme") is False

    def test_empty_both_returns_false(self):
        assert verify_credentials("", "") is False

    def test_sql_injection_in_username_rejected(self):
        """SQL-injection-style strings in credentials must simply not match."""
        assert verify_credentials("admin' OR '1'='1", "anything") is False

    def test_near_match_password_rejected(self):
        """A password that differs by one character must be rejected."""
        assert verify_credentials("admin", "changeme!") is False
