# -*- coding: utf-8 -*-
"""
Unit tests for OctoPrint Log Monitor security module.

Tests the security utilities including:
- Path validation (traversal prevention)
- File size checking
- Input validation (pagination, severity levels)
- Sensitive data masking
- Rate limiting
"""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from octoprint_logmonitor.security import (
    is_safe_path,
    validate_filename,
    check_file_size,
    validate_pagination,
    validate_severity_levels,
    mask_sensitive_data,
    RateLimiter,
    VALID_SEVERITY_LEVELS,
    MAX_FILE_SIZE_BYTES,
    MAX_SEARCH_LIMIT,
)


class TestPathValidation(unittest.TestCase):
    """Test is_safe_path() path traversal prevention."""

    def setUp(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_safe_path_simple_filename(self):
        """Test that a simple filename is safe."""
        result = is_safe_path(self.temp_dir, "octoprint.log")
        self.assertTrue(result)

    def test_safe_path_with_underscore_and_dots(self):
        """Test filename with underscores and dots."""
        result = is_safe_path(self.temp_dir, "plugin_test_123.log")
        self.assertTrue(result)

    def test_path_traversal_parent_dir(self):
        """Test that ../.. traversal is blocked."""
        result = is_safe_path(self.temp_dir, "../../etc/passwd")
        self.assertFalse(result)

    def test_path_traversal_single_parent(self):
        """Test that ../ traversal is blocked."""
        result = is_safe_path(self.temp_dir, "../other.log")
        self.assertFalse(result)

    def test_absolute_path_blocked(self):
        """Test that absolute paths are blocked."""
        result = is_safe_path(self.temp_dir, "/etc/passwd")
        self.assertFalse(result)

    def test_path_with_slashes_blocked(self):
        """Test that paths with directory separators are blocked."""
        # Note: os.path.join normalizes the path, but validate_filename
        # should be used to reject filenames with slashes before calling is_safe_path
        result = validate_filename("subdir/file.log")
        self.assertFalse(result)

    def test_empty_base_dir_rejected(self):
        """Test that empty base_dir returns False."""
        result = is_safe_path("", "file.log")
        self.assertFalse(result)

    def test_empty_filename_rejected(self):
        """Test that empty filename returns False."""
        result = is_safe_path(self.temp_dir, "")
        self.assertFalse(result)

    def test_none_base_dir_rejected(self):
        """Test that None base_dir returns False."""
        result = is_safe_path(None, "file.log")
        self.assertFalse(result)

    def test_none_filename_rejected(self):
        """Test that None filename returns False."""
        result = is_safe_path(self.temp_dir, None)
        self.assertFalse(result)


class TestFilenameValidation(unittest.TestCase):
    """Test validate_filename() for safe bare filenames."""

    def test_valid_simple_filename(self):
        """Test valid simple filename."""
        self.assertTrue(validate_filename("octoprint.log"))

    def test_valid_filename_with_underscores(self):
        """Test valid filename with underscores."""
        self.assertTrue(validate_filename("plugin_test_123.log"))

    def test_valid_filename_with_numbers(self):
        """Test valid filename with numbers."""
        self.assertTrue(validate_filename("log_2026-02-19.txt"))

    def test_forward_slash_rejected(self):
        """Test that forward slashes are rejected."""
        self.assertFalse(validate_filename("dir/file.log"))

    def test_backslash_rejected(self):
        """Test that backslashes are rejected."""
        self.assertFalse(validate_filename("dir\\file.log"))

    def test_hidden_filename_rejected(self):
        """Test that hidden files (starting with .) are rejected."""
        self.assertFalse(validate_filename(".hidden"))

    def test_current_dir_rejected(self):
        """Test that '.' is rejected."""
        self.assertFalse(validate_filename("."))

    def test_parent_dir_rejected(self):
        """Test that '..' is rejected."""
        self.assertFalse(validate_filename(".."))

    def test_empty_string_rejected(self):
        """Test that empty string is rejected."""
        self.assertFalse(validate_filename(""))

    def test_none_rejected(self):
        """Test that None is rejected."""
        self.assertFalse(validate_filename(None))

    def test_non_string_rejected(self):
        """Test that non-string types are rejected."""
        self.assertFalse(validate_filename(123))


class TestFileSizeCheck(unittest.TestCase):
    """Test check_file_size() file size guarding."""

    def setUp(self):
        """Create temporary files for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_file = Path(self.temp_dir) / "test.log"

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_small_file_within_limit(self):
        """Test that small files pass size check."""
        self.temp_file.write_text("  Small content")
        result = check_file_size(str(self.temp_file), max_bytes=1000)
        self.assertTrue(result)

    def test_file_at_limit(self):
        """Test file exactly at size limit."""
        content = "x" * 100
        self.temp_file.write_text(content)
        result = check_file_size(str(self.temp_file), max_bytes=100)
        self.assertTrue(result)

    def test_file_exceeds_limit(self):
        """Test that large files fail size check."""
        content = "x" * 200
        self.temp_file.write_text(content)
        result = check_file_size(str(self.temp_file), max_bytes=100)
        self.assertFalse(result)

    def test_missing_file(self):
        """Test that missing files return False."""
        result = check_file_size("/nonexistent/file.log")
        self.assertFalse(result)

    def test_zero_byte_limit(self):
        """Test with zero byte limit."""
        self.temp_file.write_text("content")
        result = check_file_size(str(self.temp_file), max_bytes=0)
        self.assertFalse(result)


class TestPaginationValidation(unittest.TestCase):
    """Test validate_pagination() parameter validation."""

    def test_valid_offset_and_limit(self):
        """Test valid pagination parameters."""
        valid, error = validate_pagination(0, 50)
        self.assertTrue(valid)
        self.assertEqual(error, "")

    def test_valid_offset_and_limit_at_max(self):
        """Test validation at maximum limit."""
        valid, error = validate_pagination(0, MAX_SEARCH_LIMIT)
        self.assertTrue(valid)
        self.assertEqual(error, "")

    def test_offset_negative(self):
        """Test that negative offset is rejected."""
        valid, error = validate_pagination(-1, 50)
        self.assertFalse(valid)
        self.assertIn("offset", error.lower())

    def test_limit_zero(self):
        """Test that limit of 0 is rejected."""
        valid, error = validate_pagination(0, 0)
        self.assertFalse(valid)
        self.assertIn("limit", error.lower())

    def test_limit_negative(self):
        """Test that negative limit is rejected."""
        valid, error = validate_pagination(0, -1)
        self.assertFalse(valid)
        self.assertIn("limit", error.lower())

    def test_limit_exceeds_max(self):
        """Test that limit exceeding maximum is rejected."""
        valid, error = validate_pagination(0, MAX_SEARCH_LIMIT + 1)
        self.assertFalse(valid)
        self.assertIn("maximum", error.lower())

    def test_offset_non_integer(self):
        """Test that non-integer offset is rejected."""
        valid, error = validate_pagination("invalid", 50)
        self.assertFalse(valid)

    def test_limit_non_integer(self):
        """Test that non-integer limit is rejected."""
        valid, error = validate_pagination(0, "invalid")
        self.assertFalse(valid)

    def test_large_offset(self):
        """Test that large valid offset is accepted."""
        valid, error = validate_pagination(1000000, 50)
        self.assertTrue(valid)


class TestSeverityLevelValidation(unittest.TestCase):
    """Test validate_severity_levels() severity filter validation."""

    def test_all_valid_levels(self):
        """Test all valid severity levels."""
        levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        valid, invalid = validate_severity_levels(levels)
        self.assertEqual(set(valid), VALID_SEVERITY_LEVELS)
        self.assertEqual(invalid, [])

    def test_lowercase_levels_accepted(self):
        """Test that lowercase levels are normalized to uppercase."""
        levels = ["debug", "info", "warning"]
        valid, invalid = validate_severity_levels(levels)
        self.assertEqual(set(valid), {"DEBUG", "INFO", "WARNING"})
        self.assertEqual(invalid, [])

    def test_mixed_case_levels(self):
        """Test mixed case levels are normalized."""
        levels = ["Debug", "InFo", "WARNING"]
        valid, invalid = validate_severity_levels(levels)
        self.assertEqual(set(valid), {"DEBUG", "INFO", "WARNING"})
        self.assertEqual(invalid, [])

    def test_invalid_level(self):
        """Test invalid severity level detection."""
        levels = ["DEBUG", "INVALID", "WARNING"]
        valid, invalid = validate_severity_levels(levels)
        self.assertEqual(set(valid), {"DEBUG", "WARNING"})
        self.assertEqual(invalid, ["INVALID"])

    def test_empty_levels(self):
        """Test empty levels list."""
        valid, invalid = validate_severity_levels([])
        self.assertEqual(valid, [])
        self.assertEqual(invalid, [])

    def test_none_levels(self):
        """Test None levels."""
        valid, invalid = validate_severity_levels(None)
        self.assertEqual(valid, [])
        self.assertEqual(invalid, [])

    def test_multiple_invalid_levels(self):
        """Test multiple invalid levels."""
        levels = ["TRACE", "VERBOSE", "FATAL"]
        valid, invalid = validate_severity_levels(levels)
        self.assertEqual(valid, [])
        self.assertEqual(set(invalid), {"TRACE", "VERBOSE", "FATAL"})


class TestSensitiveDataMasking(unittest.TestCase):
    """Test mask_sensitive_data() sensitive information masking."""

    def test_mask_api_key_with_equals(self):
        """Test masking API key with = separator."""
        text = "API_KEY=secret123abc"
        result = mask_sensitive_data(text)
        self.assertNotIn("secret123abc", result)
        self.assertIn("[REDACTED]", result)

    def test_mask_api_key_with_colon(self):
        """Test masking API key with : separator."""
        text = "apikey: mysecretkey"
        result = mask_sensitive_data(text)
        self.assertNotIn("mysecretkey", result)
        self.assertIn("[REDACTED]", result)

    def test_mask_password(self):
        """Test masking password."""
        text = "password=mypassword123"
        result = mask_sensitive_data(text)
        self.assertNotIn("mypassword123", result)
        self.assertIn("[REDACTED]", result)

    def test_mask_access_token(self):
        """Test masking access token."""
        text = "access_token: abc123xyz"
        result = mask_sensitive_data(text)
        self.assertNotIn("abc123xyz", result)
        self.assertIn("[REDACTED]", result)

    def test_mask_bearer_token(self):
        """Test masking bearer token."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIs"
        result = mask_sensitive_data(text)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIs", result)
        self.assertIn("[REDACTED]", result)

    def test_mask_email_address(self):
        """Test masking email addresses."""
        text = "User email: test@example.com contacted us"
        result = mask_sensitive_data(text)
        self.assertNotIn("test@example.com", result)
        self.assertIn("[EMAIL REDACTED]", result)

    def test_mask_multiple_patterns(self):
        """Test masking multiple sensitive patterns."""
        text = "api_key=secret123 password=pass456 user@example.com"
        result = mask_sensitive_data(text)
        self.assertNotIn("secret123", result)
        self.assertNotIn("pass456", result)
        self.assertNotIn("user@example.com", result)

    def test_non_sensitive_text_unchanged(self):
        """Test that non-sensitive text is unchanged."""
        text = "This is a normal log message"
        result = mask_sensitive_data(text)
        self.assertEqual(text, result)

    def test_empty_string(self):
        """Test masking empty string."""
        result = mask_sensitive_data("")
        self.assertEqual(result, "")


class TestRateLimiter(unittest.TestCase):
    """Test RateLimiter class for rate limiting."""

    def test_allow_within_quota(self):
        """Test requests within quota are allowed."""
        limiter = RateLimiter(max_calls=3, period=1.0)
        client = "client_1"
        self.assertTrue(limiter.is_allowed(client))
        self.assertTrue(limiter.is_allowed(client))
        self.assertTrue(limiter.is_allowed(client))

    def test_reject_over_quota(self):
        """Test requests over quota are rejected."""
        limiter = RateLimiter(max_calls=2, period=1.0)
        client = "client_1"
        self.assertTrue(limiter.is_allowed(client))
        self.assertTrue(limiter.is_allowed(client))
        self.assertFalse(limiter.is_allowed(client))

    def test_multiple_clients_independent(self):
        """Test that different clients have independent quotas."""
        limiter = RateLimiter(max_calls=2, period=1.0)
        self.assertTrue(limiter.is_allowed("client_1"))
        self.assertTrue(limiter.is_allowed("client_1"))
        self.assertFalse(limiter.is_allowed("client_1"))
        # client_2 should still have quota
        self.assertTrue(limiter.is_allowed("client_2"))
        self.assertTrue(limiter.is_allowed("client_2"))
        self.assertFalse(limiter.is_allowed("client_2"))

    def test_rate_limit_reset_after_period(self):
        """Test quota resets after period expires."""
        limiter = RateLimiter(max_calls=2, period=0.1)  # 100ms window
        client = "client_1"
        # Fill quota
        self.assertTrue(limiter.is_allowed(client))
        self.assertTrue(limiter.is_allowed(client))
        # Over quota
        self.assertFalse(limiter.is_allowed(client))
        # Wait for window to expire
        time.sleep(0.15)
        # Quota should reset
        self.assertTrue(limiter.is_allowed(client))

    def test_cleanup_removes_expired_entries(self):
        """Test cleanup() removes old client entries."""
        limiter = RateLimiter(max_calls=1, period=0.05)  # 50ms window
        limiter.is_allowed("client_1")
        time.sleep(0.1)
        limiter.cleanup()
        # Entry should be removed
        self.assertEqual(len(limiter._clients), 0)

    def test_cleanup_keeps_active_entries(self):
        """Test cleanup() keeps recent entries."""
        limiter = RateLimiter(max_calls=1, period=1.0)
        limiter.is_allowed("client_1")
        limiter.cleanup()
        # Recent entry should remain
        self.assertEqual(len(limiter._clients), 1)

    def test_single_call_quota(self):
        """Test rate limiter with quota of 1."""
        limiter = RateLimiter(max_calls=1, period=1.0)
        self.assertTrue(limiter.is_allowed("client"))
        self.assertFalse(limiter.is_allowed("client"))

    def test_high_quota(self):
        """Test rate limiter with high quota."""
        limiter = RateLimiter(max_calls=100, period=1.0)
        for _ in range(100):
            self.assertTrue(limiter.is_allowed("client"))
        self.assertFalse(limiter.is_allowed("client"))


if __name__ == "__main__":
    unittest.main()
