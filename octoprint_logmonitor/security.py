"""
Security Utilities Module

Centralized security helpers for the OctoPrint Log Monitor plugin.
Provides path validation, input sanitization, rate limiting, and sensitive
data masking to protect against common web security threats.
"""

import os
import re
import threading
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum allowed log file size (1 GiB). Files larger than this are rejected
#: to prevent excessive memory/CPU usage.
MAX_FILE_SIZE_BYTES: int = 1024 * 1024 * 1024  # 1 GiB

#: Hard upper bound for the ``limit`` query parameter in search requests.
MAX_SEARCH_LIMIT: int = 1000

#: Hard upper bound for alert-history ``limit`` parameter.
MAX_HISTORY_LIMIT: int = 500

#: Regex patterns used to detect and mask sensitive values in log text.
#: Each entry is a (compiled_pattern, replacement_string) pair.
_SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # API keys / tokens / secrets  (key = value  or  key: value)
    (
        re.compile(
            r"(?i)(api[_\-]?key|apikey|access[_\-]?token|auth[_\-]?token"
            r"|secret[_\-]?key|client[_\-]?secret)\s*[:=]\s*\S+",
        ),
        r"\1: [REDACTED]",
    ),
    # Passwords
    (
        re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
        r"\1: [REDACTED]",
    ),
    # E-mail addresses
    (
        re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
        "[EMAIL REDACTED]",
    ),
    # Bearer tokens in HTTP headers
    (
        re.compile(r"(?i)(bearer|basic)\s+[A-Za-z0-9+/=._~\-]{8,}"),
        r"\1 [REDACTED]",
    ),
]


# ---------------------------------------------------------------------------
# Path / Filename Validation
# ---------------------------------------------------------------------------


def is_safe_path(base_dir: str, filename: str) -> bool:
    """
    Determine whether *filename* resolves to a path inside *base_dir*.

    This prevents path-traversal attacks (``../``, absolute paths, symlink
    escapes, etc.).  Both *base_dir* and the resolved candidate path are
    canonicalised with :func:`os.path.realpath` before comparison so that
    symbolic links cannot be used to escape the allowed directory.

    Args:
        base_dir: The directory that all file access must be confined to.
        filename: A bare filename (no directory components expected) provided
                  by the user / API caller.

    Returns:
        ``True`` if and only if the resolved path is strictly inside
        (or equal to) *base_dir*.
    """
    if not base_dir or not filename:
        return False

    try:
        abs_base = os.path.realpath(os.path.abspath(base_dir))
        # Join base with the user-supplied name and resolve
        candidate = os.path.realpath(os.path.abspath(os.path.join(abs_base, filename)))
        # Candidate must start with base followed by a separator, OR equal base itself
        return candidate == abs_base or candidate.startswith(abs_base + os.sep)
    except (OSError, ValueError, TypeError):
        return False


def validate_filename(filename: str) -> bool:
    """
    Check that *filename* is a plain filename with no path components.

    Rejects:
    * Empty strings
    * Names containing ``/`` or ``\\``
    * Names starting with ``.`` (hidden / relative traversal start)
    * Names that differ from ``os.path.basename(filename)``

    Args:
        filename: The filename string to validate.

    Returns:
        ``True`` if the filename is considered safe.
    """
    if not filename or not isinstance(filename, str):
        return False
    if "/" in filename or "\\" in filename:
        return False
    if filename.startswith("."):
        return False
    # os.path.basename strips any remaining path prefix
    return os.path.basename(filename) == filename


# ---------------------------------------------------------------------------
# File Size Guard
# ---------------------------------------------------------------------------


def check_file_size(filepath: str, max_bytes: int = MAX_FILE_SIZE_BYTES) -> bool:
    """
    Return ``True`` if *filepath* exists and is within *max_bytes*.

    Files that cannot be stat-ed (missing, permissions, etc.) return
    ``False`` so the caller can handle the error appropriately.

    Args:
        filepath: Absolute path to the file.
        max_bytes: Size limit in bytes.  Defaults to :data:`MAX_FILE_SIZE_BYTES`.

    Returns:
        ``True`` if the file is within the size limit.
    """
    try:
        return os.path.getsize(filepath) <= max_bytes
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Input Validation Helpers
# ---------------------------------------------------------------------------


def validate_pagination(
    offset: int, limit: int, max_limit: int = MAX_SEARCH_LIMIT
) -> tuple[bool, str]:
    """
    Validate ``offset`` and ``limit`` pagination parameters.

    Args:
        offset: The requested result offset.
        limit: The requested result count.
        max_limit: Maximum permitted *limit* value.

    Returns:
        A ``(valid, error_message)`` tuple.  *error_message* is empty when
        *valid* is ``True``.
    """
    if not isinstance(offset, int) or offset < 0:
        return False, "offset must be a non-negative integer"
    if not isinstance(limit, int) or limit < 1:
        return False, "limit must be a positive integer"
    if limit > max_limit:
        return False, f"limit exceeds maximum of {max_limit}"
    return True, ""


VALID_SEVERITY_LEVELS = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "UNKNOWN"}
)


def validate_severity_levels(
    levels: Optional[list[str]],
) -> tuple[list[str], list[str]]:
    """
    Partition *levels* into valid and invalid severity level strings.

    Args:
        levels: User-supplied list of level strings (may be ``None``).

    Returns:
        ``(valid_levels, invalid_levels)`` where each is a list of strings.
    """
    if not levels:
        return [], []
    valid = [lvl.upper() for lvl in levels if lvl.upper() in VALID_SEVERITY_LEVELS]
    invalid = [lvl for lvl in levels if lvl.upper() not in VALID_SEVERITY_LEVELS]
    return valid, invalid


# ---------------------------------------------------------------------------
# Sensitive Data Masking
# ---------------------------------------------------------------------------


def mask_sensitive_data(text: str) -> str:
    """
    Apply all sensitive-data masking patterns to *text* and return the result.

    This can be used for optional log-output sanitisation where administrators
    want to prevent passwords, API keys, or e-mail addresses from appearing in
    streamed log content sent to the browser.

    Args:
        text: The raw log text to sanitise.

    Returns:
        The text with sensitive values replaced.
    """
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """
    Simple thread-safe sliding-window rate limiter.

    Tracks call timestamps per *client key* string (e.g. an IP address or
    user identifier).  Calls that exceed the configured quota within the
    sliding time window are rejected.

    Example::

        limiter = RateLimiter(max_calls=10, period=60.0)  # 10 req / min

        if not limiter.is_allowed(client_ip):
            return flask.jsonify({"error": "Rate limit exceeded"}), 429
    """

    def __init__(self, max_calls: int, period: float) -> None:
        """
        Initialise the rate limiter.

        Args:
            max_calls: Maximum number of calls allowed within *period*.
            period: Sliding window duration in seconds.
        """
        self._max_calls = max_calls
        self._period = period
        self._clients: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, client_key: str) -> bool:
        """
        Check whether *client_key* is within the rate limit.

        Calling this method counts as one request attempt regardless of the
        return value.

        Args:
            client_key: An opaque string identifying the caller (e.g. IP).

        Returns:
            ``True`` if the request is within quota, ``False`` if it should
            be rejected.
        """
        now = time.monotonic()
        with self._lock:
            timestamps = self._clients.get(client_key, [])
            # Evict expired timestamps
            timestamps = [t for t in timestamps if now - t < self._period]
            if len(timestamps) >= self._max_calls:
                self._clients[client_key] = timestamps
                return False
            timestamps.append(now)
            self._clients[client_key] = timestamps
            return True

    def cleanup(self) -> None:
        """Remove all fully-expired client entries to free memory."""
        now = time.monotonic()
        with self._lock:
            for key in list(self._clients.keys()):
                self._clients[key] = [
                    t for t in self._clients[key] if now - t < self._period
                ]
                if not self._clients[key]:
                    del self._clients[key]
