"""Security Utilities Module.

Centralized security helpers for the OctoPrint Log Monitor plugin.
Provides path validation, input sanitization, rate limiting, and sensitive
data masking to protect against common web security threats.
"""

import os
import re
import threading
import time
from typing import Any, Optional

try:  # pragma: no cover - import guard depends on the environment
    # The third-party ``regex`` module is a drop-in replacement for ``re``
    # that supports a per-call ``timeout``. The stdlib ``re`` has no way to
    # bound matching time, so a user-supplied pattern can pin a CPU core
    # indefinitely (ReDoS). ``regex`` is an optional dependency: when it is
    # missing we fall back to ``re`` plus a conservative pattern-complexity
    # check, which is weaker but needs no extra install.
    import regex as _regex_module

    HAS_REGEX_TIMEOUT: bool = True
except ImportError:  # pragma: no cover - exercised in the no-regex env
    _regex_module = None  # type: ignore[assignment]
    HAS_REGEX_TIMEOUT = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum allowed log file size (1 GiB). Files larger than this are rejected
#: to prevent excessive memory/CPU usage.
MAX_FILE_SIZE_BYTES: int = 1024 * 1024 * 1024  # 1 GiB

#: Hard upper bound for a log file served through the download endpoint.
#: That endpoint buffers the file in memory to pin Content-Length against a
#: file that is still being written to, so this bound is about available RAM,
#: not disk: OctoPrint commonly runs on a Pi with well under 1 GiB free.
#: Larger files are refused rather than risking the server process.
MAX_DOWNLOAD_BYTES: int = 64 * 1024 * 1024  # 64 MiB

#: Hard upper bound for the ``limit`` query parameter in search requests.
MAX_SEARCH_LIMIT: int = 1000

#: Hard upper bound for alert-history ``limit`` parameter.
MAX_HISTORY_LIMIT: int = 500

#: Hard upper bound for the length of a user-supplied search query/regex.
#: Note: this is an input-size guard only. It does NOT prevent catastrophic
#: backtracking -- a pattern such as ``(x+)+$`` is six characters long and can
#: still hang a backtracking engine indefinitely. ReDoS is handled separately
#: by the execution timeout in :func:`compile_search_pattern` /
#: :func:`search_with_timeout`.
MAX_QUERY_LENGTH: int = 200

#: Wall-clock budget for a single regex match attempt, in seconds. A
#: user-supplied pattern that exceeds this on one line is aborted rather than
#: allowed to pin a CPU core. Only enforced when the ``regex`` module is
#: available (see :data:`HAS_REGEX_TIMEOUT`).
REGEX_TIMEOUT_SECONDS: float = 0.25

#: Maximum number of lines a single search request may scan. Bounds the total
#: work of one request even when every individual match stays under
#: :data:`REGEX_TIMEOUT_SECONDS`.
MAX_SCAN_LINES: int = 500_000

#: Regex patterns used to detect and mask sensitive values in log text.
#: Each entry is a (compiled_pattern, replacement_string) pair.
_SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # API keys / tokens / secrets  (key = value  or  key: value)
    (
        re.compile(
            r"(?i)(api[_\-]?key|apikey|access[_\-]?token|auth[_\-]?token|secret[_\-]?key|client[_\-]?secret)\s*[:=]\s*\S+",  # noqa: E501
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
    """Determine whether *filename* resolves to a path inside *base_dir*.

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
        candidate = os.path.realpath(
            os.path.abspath(os.path.join(abs_base, filename))
        )
        # Candidate must start with base followed by a separator, OR equal base
        # itself
        return candidate == abs_base or candidate.startswith(abs_base + os.sep)
    except (OSError, ValueError, TypeError):
        return False


def validate_filename(filename: str) -> bool:
    """Check that *filename* is a plain filename with no path components.

    Rejects:
    * Empty strings
    * Names containing path separators (``/`` or backslash)
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


def check_file_size(
    filepath: str,
    max_bytes: int = MAX_FILE_SIZE_BYTES,
) -> bool:
    """Return ``True`` if *filepath* exists and is within *max_bytes*.

    Files that cannot be stat-ed (missing, permissions, etc.) return
    ``False`` so the caller can handle the error appropriately.

    Args:
        filepath: Absolute path to the file.
        max_bytes: Size limit in bytes.  Defaults to
            :data:`MAX_FILE_SIZE_BYTES`.

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
    """Validate ``offset`` and ``limit`` pagination parameters.

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
    """Partition *levels* into valid and invalid severity level strings.

    Args:
        levels: User-supplied list of level strings (may be ``None``).

    Returns:
        ``(valid_levels, invalid_levels)`` where each is a list of strings.
    """
    if not levels:
        return [], []
    valid = [
        lvl.upper() for lvl in levels if lvl.upper() in VALID_SEVERITY_LEVELS
    ]
    invalid = [
        lvl for lvl in levels if lvl.upper() not in VALID_SEVERITY_LEVELS
    ]
    return valid, invalid


# ---------------------------------------------------------------------------
# Sensitive Data Masking
# ---------------------------------------------------------------------------


def mask_sensitive_data(text: str) -> str:
    """Apply all sensitive-data masking patterns to *text*.

    Returns the sanitised result. This can be used for optional log-output
    sanitisation where administrators
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
    """Simple thread-safe sliding-window rate limiter.

    Tracks call timestamps per *client key* string (e.g. an IP address or
    user identifier).  Calls that exceed the configured quota within the
    sliding time window are rejected.

    Example::

        limiter = RateLimiter(max_calls=10, period=60.0)  # 10 req / min

        if not limiter.is_allowed(client_ip):
            return flask.jsonify({"error": "Rate limit exceeded"}), 429
    """

    def __init__(self, max_calls: int, period: float) -> None:
        """Initialise the rate limiter.

        Args:
            max_calls: Maximum number of calls allowed within *period*.
            period: Sliding window duration in seconds.
        """
        self._max_calls = max_calls
        self._period = period
        self._clients: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    def is_allowed(self, client_key: str) -> bool:
        """Check whether *client_key* is within the rate limit.

        Calling this method counts as one request attempt regardless of the
        return value.  Fully-expired client entries are pruned automatically
        once per sliding-window period, so the tracking dict cannot grow
        without bound.

        Args:
            client_key: An opaque string identifying the caller (e.g. IP).

        Returns:
            ``True`` if the request is within quota, ``False`` if it should
            be rejected.
        """
        now = time.monotonic()
        with self._lock:
            if now - self._last_cleanup >= self._period:
                self._cleanup_locked(now)
                self._last_cleanup = now

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
        with self._lock:
            self._cleanup_locked(time.monotonic())

    def _cleanup_locked(self, now: float) -> None:
        """Prune expired entries; caller must hold ``self._lock``."""
        for key in list(self._clients.keys()):
            remaining = [
                t for t in self._clients[key] if now - t < self._period
            ]
            if remaining:
                self._clients[key] = remaining
            else:
                del self._clients[key]


# ---------------------------------------------------------------------------
# Regex execution safety (ReDoS mitigation)
# ---------------------------------------------------------------------------

#: Characters that act as a quantifier directly after a group.
_QUANTIFIER_CHARS = frozenset("*+{")


#: Exception type(s) raised for invalid regex syntax by whichever engine is
#: in use. ``regex.error`` does NOT subclass ``re.error``, so both must be
#: caught; callers should use this tuple rather than ``re.error`` alone.
PATTERN_SYNTAX_ERRORS: tuple = (
    (re.error, _regex_module.error) if HAS_REGEX_TIMEOUT else (re.error,)
)


class UnsafePatternError(ValueError):
    """Raised when a user-supplied regex is rejected as unsafe to execute."""


class PatternTimeoutError(Exception):
    """Raised when a regex match exceeds :data:`REGEX_TIMEOUT_SECONDS`."""


def _looks_catastrophic(pattern: str) -> bool:
    r"""Report whether a pattern has a shape known to backtrack badly.

    This is a deliberately coarse heuristic used only when the ``regex``
    module (and therefore a real execution timeout) is unavailable. It
    rejects nested quantifiers such as ``(x+)+`` and quantified
    alternations such as ``(a|a)*``.

    Implemented as a single left-to-right scan rather than a regular
    expression: matching this shape with a regex needs nested character
    classes whose runtime grows quadratically with the input, which would
    make the ReDoS guard a ReDoS vector itself. The scan below is O(n) and
    allocates nothing.

    It errs towards refusing: some nested shapes it rejects would in fact
    run fine. That trade is deliberate -- this path is only reached when no
    execution timeout is available, where a false refusal costs a search
    and a false pass can cost the server. It also tracks escaping and
    character classes, so ``\(x+\)+`` and ``[a*+]+`` are correctly
    allowed where a regex-based check rejected them.

    Args:
        pattern: The raw, user-supplied regular expression source.

    Returns:
        True if the pattern should be refused.
    """
    # Track, per open group, whether it contains a quantifier or an
    # alternation. When the group closes and is itself quantified, that is
    # the nested-quantifier shape we refuse.
    risky_stack: list[bool] = []
    escaped = False
    in_class = False
    index = 0
    length = len(pattern)

    while index < length:
        char = pattern[index]

        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif in_class:
            # Inside [...] the quantifier characters are literals.
            if char == "]":
                in_class = False
        elif char == "[":
            in_class = True
        elif char == "(":
            risky_stack.append(False)
        elif char == ")":
            risky = risky_stack.pop() if risky_stack else False
            # Skip whitespace between the group and its quantifier.
            probe = index + 1
            while probe < length and pattern[probe].isspace():
                probe += 1
            quantified = probe < length and pattern[probe] in _QUANTIFIER_CHARS
            if risky and quantified:
                return True
            # A quantified group is itself a risk marker for any group
            # enclosing it.
            if quantified and risky_stack:
                risky_stack[-1] = True
        elif char in _QUANTIFIER_CHARS or char == "|":
            if risky_stack:
                risky_stack[-1] = True

        index += 1

    return False


def compile_search_pattern(
    query: str,
    *,
    use_regex: bool,
    case_sensitive: bool,
) -> Any:
    """Compile a user-supplied search query into a safe pattern object.

    Literal searches are escaped, so they are always safe. Regex searches
    are compiled with the ``regex`` module when available, which allows a
    per-call execution timeout; otherwise they are screened with
    :func:`_looks_catastrophic` and refused if they look dangerous.

    Args:
        query: Raw search text or regular expression from the client.
        use_regex: True to treat ``query`` as a regular expression.
        case_sensitive: True for a case-sensitive match.

    Returns:
        A compiled pattern object (``regex.Pattern`` or ``re.Pattern``).

    Raises:
        UnsafePatternError: The pattern is refused as likely-catastrophic.
        re.error: The pattern is not valid regular expression syntax.
    """
    engine = _regex_module if HAS_REGEX_TIMEOUT else re
    flags = 0 if case_sensitive else engine.IGNORECASE

    if not use_regex:
        # A literal search can never backtrack pathologically once escaped.
        return engine.compile(engine.escape(query), flags)

    if not HAS_REGEX_TIMEOUT and _looks_catastrophic(query):
        raise UnsafePatternError(
            "Pattern rejected: nested quantifiers can cause excessive "
            "backtracking. Install the 'regex' package to allow it, or "
            "simplify the expression."
        )

    return engine.compile(query, flags)


def search_with_timeout(pattern: Any, text: str) -> bool:
    """Run ``pattern`` against ``text`` under a wall-clock budget.

    Args:
        pattern: A compiled pattern from :func:`compile_search_pattern`.
        text: The subject string (a single log line or message).

    Returns:
        True if the pattern matches.

    Raises:
        PatternTimeoutError: Matching exceeded
            :data:`REGEX_TIMEOUT_SECONDS`. Only possible when the ``regex``
            module is installed; the stdlib fallback cannot interrupt a
            running match.
    """
    if not HAS_REGEX_TIMEOUT:
        return bool(pattern.search(text))

    try:
        return bool(pattern.search(text, timeout=REGEX_TIMEOUT_SECONDS))
    except TimeoutError as exc:
        # regex>=2022 raises the builtin TimeoutError on expiry.
        raise PatternTimeoutError(
            "Search pattern exceeded its time budget"
        ) from exc
