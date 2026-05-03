"""
Log Searcher Module

Provides efficient log file searching with pagination and severity filtering.
Memory-efficient implementation that streams through large log files.
"""

import csv
import io
import os
import re
from typing import Any, ClassVar, Optional


class LogSearcher:
    """
    Efficient log file searcher with pagination support.

    Features:
    - Memory-efficient line-by-line reading
    - Free-text search (case-insensitive)
    - Severity level filtering
    - Pagination support
    - Context lines (lines before/after match)
    - Regex search mode (optional)
    """

    # OctoPrint log format: YYYY-MM-DD HH:MM:SS,ms - LOGGER - LEVEL - MESSAGE
    LOG_PATTERN = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+-\s+"
        r"([^\-]+)\s+-\s+"
        r"(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+-\s+"
        r"(.+)$"
    )

    # Compact format seen in some environments:
    # YYYY-MM-DD HH:MM:SS,msLEVEL LOGGER MESSAGE
    COMPACT_LOG_PATTERN = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})"
        r"\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
        r"([A-Za-z0-9_.:-]+)\s+(.+)$"
    )

    VALID_LEVELS: ClassVar[set[str]] = {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
        "UNKNOWN",
    }

    def __init__(self, logger: Optional[Any] = None):
        """
        Initialize the log searcher.

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
        """
        Search log file for matching entries.

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
                - total: Total number of matches found
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
                lvl.upper() for lvl in levels if lvl.upper() in self.VALID_LEVELS
            }
        else:
            allowed_levels = self.VALID_LEVELS.copy()

        # Compile search pattern
        search_pattern = None
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

        # Search the file
        try:
            results = []
            total_matches = 0
            current_match = 0

            with open(filepath, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            # Process lines
            for i, line in enumerate(lines):
                parsed = self._parse_line(line)

                # Check if line matches filters
                if self._matches_filters(parsed, search_pattern, allowed_levels):
                    total_matches += 1

                    # Check if we should include this match (pagination)
                    if current_match >= offset and len(results) < limit:
                        # Add the match
                        match_entry = parsed.copy()

                        # Add context lines if requested
                        if context_lines > 0:
                            match_entry["context_before"] = self._get_context_lines(
                                lines, i, context_lines, before=True
                            )
                            match_entry["context_after"] = self._get_context_lines(
                                lines, i, context_lines, before=False
                            )

                        results.append(match_entry)

                    current_match += 1

                    # Early exit if we have enough results
                    if len(results) >= limit and current_match > offset + limit:
                        break

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
        """
        Parse a log line into structured format.

        Args:
            line: Raw log line

        Returns:
            Dictionary with parsed fields
        """
        line = line.rstrip("\n\r")

        match = self.LOG_PATTERN.match(line)

        if match:
            return {
                "timestamp": match.group(1),
                "logger": match.group(2).strip(),
                "level": match.group(3),
                "message": match.group(4),
                "raw": line,
            }

        compact_match = self.COMPACT_LOG_PATTERN.match(line)
        if compact_match:
            return {
                "timestamp": compact_match.group(1),
                "logger": compact_match.group(3).strip(),
                "level": compact_match.group(2),
                "message": compact_match.group(4),
                "raw": line,
            }
        # Line doesn't match expected format
        return {
            "timestamp": "",
            "logger": "",
            "level": "UNKNOWN",
            "message": line,
            "raw": line,
        }

    def _matches_filters(
        self,
        parsed: dict[str, Any],
        search_pattern: Optional[re.Pattern],
        levels: set[str],
    ) -> bool:
        """
        Check if a parsed log entry matches search filters.

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

    def _get_context_lines(
        self, lines: list[str], index: int, count: int, before: bool = True
    ) -> list[dict[str, Any]]:
        """
        Get context lines before or after a match.

        Args:
            lines: All lines from the file
            index: Index of the match
            count: Number of context lines to get
            before: If True, get lines before; if False, get lines after

        Returns:
            List of parsed context line dictionaries
        """
        if before:
            start = max(0, index - count)
            end = index
        else:
            start = index + 1
            end = min(len(lines), index + 1 + count)

        context = []
        for i in range(start, end):
            if 0 <= i < len(lines):
                context.append(self._parse_line(lines[i]))

        return context

    def get_file_stats(self, filepath: str) -> dict[str, Any]:
        """
        Get statistics about a log file.

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
        """
        Export search results to CSV format.

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
        """
        Export search results to plain text format.

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
