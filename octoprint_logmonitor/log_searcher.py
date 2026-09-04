"""Log Searcher Module.

Provides efficient log file searching with pagination and severity filtering.
Memory-efficient implementation that streams through large log files
line by line instead of loading them into memory.
"""

import csv
import io
import os
import re
from collections import deque
from typing import Any, ClassVar, Optional

from .log_parser import parse_line
from .security import MAX_QUERY_LENGTH


class LogSearcher:
    """Efficient log file searcher with pagination support.

    Features:
    - Memory-efficient line-by-line streaming (never loads the whole file)
    - Free-text search (case-insensitive)
    - Severity level filtering
    - Pagination support
    - Context lines (lines before/after match)
    - Regex search mode (optional)
    """

    VALID_LEVELS: ClassVar[set[str]] = {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
        "UNKNOWN",
    }

    def __init__(self, logger: Optional[Any] = None):
        """Initialize the log searcher.

        Args:
            logger: Optional logger instance for debugging
        """
        self._logger = logger

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    # pylint: disable=too-many-locals,too-many-branches
    def search(
        self,
        filepath: str,
        query: str = "",
        levels: Optional[list[str]] = None,
        offset: int = 0,
        limit: int = 50,
        case_sensitive: bool = False,
        use_regex: bool = False,
        context_lines: int = 0,
    ) -> dict[str, Any]:
        """Search log file for matching entries.

        The file is streamed line by line; memory usage is bounded by
        ``limit`` and ``context_lines``, not by file size.  Scanning stops
        early once the requested page (plus one look-ahead match) is
        complete, so ``total`` is exact only up to that point and should be
        read as "at least this many matches".

        Args:
            filepath: Path to the log file
            query: Search query (free text or regex)
            levels: List of severity levels to filter by (None = all levels)
            offset: Number of matches to skip (for pagination)
            limit: Maximum number of results to return
            case_sensitive: Whether search should be case-sensitive
            use_regex: Whether to treat query as regex pattern
            context_lines: Number of lines to include before/after each match

        Returns:
            Dictionary with:
                - results: List of matching log entries
                - total: Number of matches found before scanning stopped
                - offset: Current offset
                - limit: Current limit
        """
        if not os.path.exists(filepath):
            if self._logger:
                self._logger.error(f"Log file not found: {filepath}")
            return {
                "results": [],
                "total": 0,
                "offset": offset,
                "limit": limit,
                "error": "Log file not found",
            }

        # Validate and normalize severity levels
        if levels is not None:
            allowed_levels: set[str] = {
                lvl.upper()
                for lvl in levels
                if lvl.upper() in self.VALID_LEVELS
            }
        else:
            allowed_levels = self.VALID_LEVELS.copy()

        # Compile search pattern
        search_pattern = None
        if query and len(query) > MAX_QUERY_LENGTH:
            if self._logger:
                self._logger.error(
                    f"Search query rejected: exceeds {MAX_QUERY_LENGTH} "
                    "characters"
                )
            return {
                "results": [],
                "total": 0,
                "offset": offset,
                "limit": limit,
                "error": f"Query exceeds maximum length of "
                f"{MAX_QUERY_LENGTH} characters",
            }
        if query:
            try:
                if use_regex:
                    flags = 0 if case_sensitive else re.IGNORECASE
                    search_pattern = re.compile(query, flags)
                else:
                    # Escape regex special characters for literal search
                    escaped_query = re.escape(query)
                    flags = 0 if case_sensitive else re.IGNORECASE
                    search_pattern = re.compile(escaped_query, flags)
            except re.error as e:
                if self._logger:
                    self._logger.error(f"Invalid regex pattern: {e}")
                return {
                    "results": [],
                    "total": 0,
                    "offset": offset,
                    "limit": limit,
                    "error": f"Invalid search pattern: {e}",
                }

        # Stream through the file
        try:
            results: list[dict[str, Any]] = []
            total_matches = 0
            current_match = 0

            # Sliding window of parsed lines preceding the current one.
            before_buffer: Optional[deque] = (
                deque(maxlen=context_lines) if context_lines > 0 else None
            )
            # Matches still waiting for their after-context to fill up:
            # list of [entry, remaining_line_count] pairs.
            pending_after: list[list[Any]] = []

            with open(filepath, encoding="utf-8", errors="replace") as f:
                for line in f:
                    parsed = self._parse_line(line)

                    # Feed after-context of earlier matches first, so the
                    # match line itself is not part of its own context.
                    if pending_after:
                        for item in pending_after:
                            item[0]["context_after"].append(parsed)
                            item[1] -= 1
                        pending_after = [
                            item for item in pending_after if item[1] > 0
                        ]

                    if self._matches_filters(
                        parsed, search_pattern, allowed_levels
                    ):
                        total_matches += 1

                        # Include this match on the requested page
                        if current_match >= offset and len(results) < limit:
                            match_entry = parsed.copy()

                            if context_lines > 0:
                                match_entry["context_before"] = list(
                                    before_buffer or ()
                                )
                                match_entry["context_after"] = []
                                pending_after.append(
                                    [match_entry, context_lines]
                                )

                            results.append(match_entry)

                        current_match += 1

                        # Early exit once the page is full, one extra match
                        # confirmed (so callers can detect further pages) and
                        # all after-context collected.
                        if (
                            len(results) >= limit
                            and current_match > offset + limit
                            and not pending_after
                        ):
                            break

                    if before_buffer is not None:
                        before_buffer.append(parsed)

            return {
                "results": results,
                "total": total_matches,
                "offset": offset,
                "limit": limit,
            }

        except OSError as e:
            if self._logger:
                self._logger.error(f"Error searching log file: {e}")
            return {
                "results": [],
                "total": 0,
                "offset": offset,
                "limit": limit,
                "error": "An error occurred while searching the log file",
            }

    def _parse_line(self, line: str) -> dict[str, Any]:
        """Parse a log line into structured format.

        Args:
            line: Raw log line

        Returns:
            Dictionary with parsed fields (see
            :func:`octoprint_logmonitor.log_parser.parse_line`)
        """
        return parse_line(line)

    def _matches_filters(
        self,
        parsed: dict[str, Any],
        search_pattern: Optional[re.Pattern],
        levels: set[str],
    ) -> bool:
        """Check if a parsed log entry matches search filters.

        Args:
            parsed: Parsed log entry
            search_pattern: Compiled regex pattern (or None for no text filter)
            levels: Set of allowed severity levels

        Returns:
            True if entry matches all filters
        """
        # Check severity level
        if parsed["level"] not in levels:
            return False

        if not search_pattern:
            return True

        # Search in message field, fall back to full raw line
        return bool(
            search_pattern.search(parsed["message"])
            or search_pattern.search(parsed["raw"])
        )

    def get_file_stats(self, filepath: str) -> dict[str, Any]:
        """Get statistics about a log file.

        Args:
            filepath: Path to the log file

        Returns:
            Dictionary with file statistics
        """
        if not os.path.exists(filepath):
            return {"exists": False, "error": "File not found"}

        try:
            stats = os.stat(filepath)

            # Count lines and severity levels
            level_counts = {level: 0 for level in self.VALID_LEVELS}
            level_counts["UNKNOWN"] = 0
            total_lines = 0

            with open(filepath, encoding="utf-8", errors="replace") as f:
                for line in f:
                    total_lines += 1
                    parsed = self._parse_line(line)
                    level = parsed["level"]
                    if level in level_counts:
                        level_counts[level] += 1

            return {
                "exists": True,
                "size_bytes": stats.st_size,
                "total_lines": total_lines,
                "level_counts": level_counts,
                "modified_time": stats.st_mtime,
            }

        except OSError as e:
            if self._logger:
                self._logger.error(f"Error getting file stats: {e}")
            return {"exists": True, "error": str(e)}

    def export_to_csv(self, results: list[dict[str, Any]]) -> str:
        """Export search results to CSV format.

        Args:
            results: List of search result dictionaries

        Returns:
            CSV string
        """
        output = io.StringIO()
        writer = csv.DictWriter(
            output, fieldnames=["timestamp", "logger", "level", "message"]
        )

        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "timestamp": result.get("timestamp", ""),
                    "logger": result.get("logger", ""),
                    "level": result.get("level", ""),
                    "message": result.get("message", ""),
                }
            )

        return output.getvalue()

    def export_to_txt(self, results: list[dict[str, Any]]) -> str:
        """Export search results to plain text format.

        Args:
            results: List of search result dictionaries

        Returns:
            Plain text string
        """
        lines = []
        for result in results:
            timestamp = result.get("timestamp", "")
            logger = result.get("logger", "")
            level = result.get("level", "")
            message = result.get("message", "")

            # Format: TIMESTAMP - LOGGER - LEVEL - MESSAGE
            line = f"{timestamp} - {logger} - {level} - {message}"
            lines.append(line)

        return "\n".join(lines)
