"""
Tests for LogSearcher class.
"""

import os
import tempfile
import time
import unittest
from pathlib import Path

from octoprint_logmonitor.log_searcher import LogSearcher
from octoprint_logmonitor.security import MAX_SCAN_LINES


class TestLogSearcher(unittest.TestCase):
    """Test cases for LogSearcher functionality."""

    def setUp(self):
        """Create a temporary log file with test data."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = Path(self.temp_dir) / "test.log"

        # Create test log content
        test_lines = [
            "2024-01-01 10:00:00,000 - octoprint - DEBUG - Debug msg\n",
            "2024-01-01 10:00:01,000 - plugin.test - INFO - Info msg\n",
            "2024-01-01 10:00:02,000 - octoprint - WARNING - Warn\n",
            "2024-01-01 10:00:03,000 - plugin.test - ERROR - Error\n",
            "2024-01-01 10:00:04,000 - octoprint - CRITICAL - Crit\n",
            "2024-01-01 10:00:05,000 - plugin.test - INFO - Test\n",
            "2024-01-01 10:00:06,000 - octoprint - DEBUG - Another\n",
            "2024-01-01 10:00:07,000 - plugin.test - ERROR - Fail\n",
        ]
        self.log_file.write_text("".join(test_lines))
        self.searcher = LogSearcher()

    def tearDown(self):
        """Clean up temporary files."""
        if self.log_file.exists():
            self.log_file.unlink()
        try:
            os.rmdir(self.temp_dir)
        except OSError:
            pass  # Directory might not be empty

    def test_search_all_lines(self):
        """Test searching without filters returns all lines."""
        result = self.searcher.search(
            filepath=str(self.log_file),
            query="",
            levels=None,
            offset=0,
            limit=100,
        )

        self.assertEqual(result["total"], 8)
        self.assertEqual(len(result["results"]), 8)

    def test_search_text_query(self):
        """Test text search."""
        result = self.searcher.search(
            filepath=str(self.log_file),
            query="Error",
            levels=None,
            offset=0,
            limit=100,
        )

        # Should match lines containing "Error" in any field
        self.assertGreater(result["total"], 0)
        self.assertLessEqual(result["total"], 3)

        # Check that Error appears somewhere in the line
        for line in result["results"]:
            line_text = f"{line['message']} {line['level']} {line['logger']}"
            self.assertIn("error", line_text.lower())

    def test_search_regex_query(self):
        """Test regex search."""
        result = self.searcher.search(
            filepath=str(self.log_file),
            query=r"plugin\.\w+",
            levels=None,
            offset=0,
            limit=100,
            use_regex=True,
        )

        # Should match lines with "plugin.test" logger
        self.assertGreater(result["total"], 0)

        for line in result["results"]:
            self.assertRegex(line["logger"], r"plugin\.\w+")

    def test_search_severity_filter(self):
        """Test filtering by severity levels."""
        # Filter for ERROR and CRITICAL only
        result = self.searcher.search(
            filepath=str(self.log_file),
            query="",
            levels=["ERROR", "CRITICAL"],
            offset=0,
            limit=100,
        )

        self.assertEqual(result["total"], 3)
        for line in result["results"]:
            self.assertIn(line["level"], ["ERROR", "CRITICAL"])

    def test_search_combined_filters(self):
        """Test combining text query and severity filter."""
        result = self.searcher.search(
            filepath=str(self.log_file),
            query="plugin",
            levels=["ERROR"],
            offset=0,
            limit=100,
        )

        # Should match only ERROR lines from plugin.test logger
        self.assertGreater(result["total"], 0)

        for line in result["results"]:
            self.assertEqual(line["level"], "ERROR")
            self.assertIn("plugin", line["logger"])

    def test_pagination(self):
        """Test pagination of search results."""
        # Page 1 (offset=0), size 3
        # Note: Empty query with no level filter returns lines
        # that match the default level set
        result_page1 = self.searcher.search(
            filepath=str(self.log_file),
            query="",
            levels=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            offset=0,
            limit=3,
        )

        # Should get all 8 lines total
        self.assertGreaterEqual(result_page1["total"], 3)
        self.assertEqual(len(result_page1["results"]), 3)

        # Page 2 (offset=3), size 3
        result_page2 = self.searcher.search(
            filepath=str(self.log_file),
            query="",
            levels=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            offset=3,
            limit=3,
        )

        self.assertEqual(len(result_page2["results"]), 3)

        # Results should be different (different timestamps)
        self.assertNotEqual(
            result_page1["results"][0]["timestamp"],
            result_page2["results"][0]["timestamp"],
        )

    def test_get_file_stats(self):
        """Test retrieval of file statistics."""
        stats = self.searcher.get_file_stats(str(self.log_file))

        self.assertIn("size_bytes", stats)
        self.assertIn("modified_time", stats)
        self.assertIn("total_lines", stats)

        self.assertEqual(stats["total_lines"], 8)
        self.assertGreater(stats["size_bytes"], 0)

    def test_invalid_file(self):
        """Test behavior with non-existent file."""
        result = self.searcher.search(
            filepath="/nonexistent/file.log",
            query="",
            levels=None,
            offset=0,
            limit=10,
        )

        self.assertEqual(result["total"], 0)
        self.assertEqual(len(result["results"]), 0)
        self.assertIn("error", result)

    def test_invalid_regex(self):
        """Test handling of invalid regex pattern."""
        result = self.searcher.search(
            filepath=str(self.log_file),
            query="[invalid(",
            levels=None,
            offset=0,
            limit=10,
            use_regex=True,
        )

        # Should return error
        self.assertIn("error", result)

    def test_search_compact_warning_line_matches_severity_filter(self):
        """Compact warning lines should be parsed as WARNING in search mode."""
        compact_file = Path(self.temp_dir) / "compact.log"
        compact_file.write_text(
            "2026-05-03 22:20:17,441WARNING octoprint.plugins.logmonitor "
            "The templates of this plugin are currently not being"
            " autoescaped\n"
        )

        result = self.searcher.search(
            filepath=str(compact_file),
            query="",
            levels=["WARNING"],
            offset=0,
            limit=10,
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["results"][0]["level"], "WARNING")
        self.assertEqual(
            result["results"][0]["logger"], "octoprint.plugins.logmonitor"
        )

        compact_file.unlink()

    def test_search_unknown_filter_only_returns_unknown(self):
        """UNKNOWN filter should return only parser-unclassified lines."""
        mixed_file = Path(self.temp_dir) / "mixed.log"
        mixed_file.write_text(
            "2024-01-01 10:00:00,000 - octoprint - INFO - Known\n"
            "unparsed line without octoprint format\n"
        )

        result = self.searcher.search(
            filepath=str(mixed_file),
            query="",
            levels=["UNKNOWN"],
            offset=0,
            limit=10,
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["results"][0]["level"], "UNKNOWN")
        self.assertIn("unparsed line", result["results"][0]["message"])

        mixed_file.unlink()

    def test_search_explicit_levels_exclude_unknown_when_not_selected(self):
        """UNKNOWN lines should be excluded when levels
        do not include UNKNOWN."""
        mixed_file = Path(self.temp_dir) / "mixed_levels.log"
        mixed_file.write_text(
            "2024-01-01 10:00:00,000 - octoprint - INFO - Known\n"
            "unparsed line without octoprint format\n"
        )

        result = self.searcher.search(
            filepath=str(mixed_file),
            query="",
            levels=["INFO"],
            offset=0,
            limit=10,
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["results"][0]["level"], "INFO")

        mixed_file.unlink()

    def test_empty_file(self):
        """Test searching in empty file."""
        empty_file = Path(self.temp_dir) / "empty.log"
        empty_file.touch()

        result = self.searcher.search(
            filepath=str(empty_file),
            query="test",
            levels=None,
            offset=0,
            limit=10,
        )

        self.assertEqual(result["total"], 0)
        self.assertEqual(len(result["results"]), 0)

        empty_file.unlink()

    def test_search_with_context_lines(self):
        """Context lines should include neighboring entries around a match."""
        context_file = Path(self.temp_dir) / "context.log"
        context_file.write_text(
            "line 1\n"
            "line 2\n"
            "2024-01-01 10:00:03,000 - plugin.test - ERROR - target\n"
            "line 4\n"
            "line 5\n"
        )

        result = self.searcher.search(
            filepath=str(context_file),
            query="target",
            levels=None,
            offset=0,
            limit=10,
            context_lines=1,
        )

        self.assertEqual(result["total"], 1)
        self.assertGreaterEqual(len(result["results"]), 1)
        context_file.unlink()

    def test_search_with_large_offset_returns_empty_page(self):
        """Offset above match count should return an empty result page."""
        result = self.searcher.search(
            filepath=str(self.log_file),
            query="",
            levels=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            offset=1000,
            limit=10,
        )

        self.assertEqual(result["total"], 8)
        self.assertEqual(len(result["results"]), 0)

    def test_search_special_chars_are_literal_in_plain_mode(self):
        """Literal search should handle regex metacharacters safely."""
        special_file = Path(self.temp_dir) / "special.log"
        special_file.write_text("price: $100 (50% off)\n")

        result = self.searcher.search(
            filepath=str(special_file),
            query="$100",
            levels=None,
            offset=0,
            limit=10,
            use_regex=False,
        )

        self.assertEqual(result["total"], 1)
        special_file.unlink()

    def test_search_case_sensitive(self):
        """Case-sensitive mode should not match different casing."""
        case_file = Path(self.temp_dir) / "case.log"
        case_file.write_text("Error\nerror\nERROR\n")

        result = self.searcher.search(
            filepath=str(case_file),
            query="Error",
            levels=None,
            offset=0,
            limit=10,
            case_sensitive=True,
        )

        self.assertEqual(result["total"], 1)
        case_file.unlink()

    def test_search_binary_file_uses_replace_error_handler(self):
        """Binary content should not crash search due to
        UTF-8 decode errors."""
        binary_file = Path(self.temp_dir) / "binary.log"
        with open(binary_file, "wb") as f:
            f.write(b"line 1\nline\xff2\n")

        result = self.searcher.search(
            filepath=str(binary_file),
            query="line",
            levels=None,
            offset=0,
            limit=10,
        )

        self.assertIn("total", result)
        self.assertIsInstance(result["results"], list)
        binary_file.unlink()


if __name__ == "__main__":
    unittest.main()


class TestRegexDoSProtection(unittest.TestCase):
    """Regression tests for the ReDoS fix (CodeQL py/regex-injection).

    A user-supplied regex reaches ``re.search`` via the /search endpoint.
    Patterns such as ``(x+)+$`` are only a handful of characters long, so
    MAX_QUERY_LENGTH cannot stop them, and the stdlib ``re`` has no way to
    bound matching time.
    """

    #: Patterns that hang a backtracking engine on a non-matching subject.
    EVIL_PATTERNS = (r"(x+)+$", r"(x|x)*$", r"(a*)*$")

    def setUp(self):
        """Create a log file whose lines trigger worst-case backtracking."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = Path(self.temp_dir) / "redos.log"
        payload = "x" * 40 + "!"
        self.log_file.write_text(
            f"2024-01-01 10:00:00,000 - octoprint - ERROR - {payload}\n" * 5
        )
        self.searcher = LogSearcher()

    def tearDown(self):
        """Remove the temporary log file."""
        if self.log_file.exists():
            self.log_file.unlink()
        try:
            os.rmdir(self.temp_dir)
        except OSError:
            pass

    def test_evil_patterns_complete_quickly(self):
        """A catastrophic pattern must not hang the search."""
        for pattern in self.EVIL_PATTERNS:
            with self.subTest(pattern=pattern):
                start = time.monotonic()
                result = self.searcher.search(
                    str(self.log_file), query=pattern, use_regex=True
                )
                elapsed = time.monotonic() - start

                # Generous bound: the point is "returns", not "is fast".
                self.assertLess(
                    elapsed,
                    15.0,
                    f"{pattern!r} took {elapsed:.1f}s - ReDoS not mitigated",
                )
                # It must fail loudly, not silently return bogus matches.
                self.assertIsInstance(result, dict)

    def test_benign_regex_still_works(self):
        """The fix must not break legitimate regex search."""
        result = self.searcher.search(
            str(self.log_file), query=r"ERROR - x+!", use_regex=True
        )
        self.assertNotIn("error", result)
        self.assertEqual(result["total"], 5)

    def test_literal_search_unaffected(self):
        """Literal search of regex metacharacters stays safe and exact."""
        result = self.searcher.search(
            str(self.log_file), query="(x+)+$", use_regex=False
        )
        self.assertNotIn("error", result)
        self.assertEqual(result["total"], 0)

    def test_invalid_pattern_returns_error_not_exception(self):
        """Bad syntax yields an error dict regardless of regex engine.

        ``regex.error`` does not subclass ``re.error``, so catching only
        ``re.error`` would let this escape as a 500.
        """
        result = self.searcher.search(
            str(self.log_file), query=r"(unclosed", use_regex=True
        )
        self.assertIn("error", result)
        self.assertEqual(result["results"], [])

    def test_scan_stops_at_line_budget(self):
        """Scanning is bounded when a query matches nothing.

        The existing early-exit only fires once a result page is full, so
        it does not bound a query with few or no matches -- that case has
        to read every line. MAX_SCAN_LINES is what caps it.
        """
        big = Path(self.temp_dir) / "big.log"
        line = "2024-01-01 10:00:00,000 - octoprint - ERROR - hit\n"
        big.write_text(line * (MAX_SCAN_LINES + 100))
        try:
            result = self.searcher.search(
                str(big), query="nomatch-zzz", use_regex=False, limit=5
            )
            self.assertTrue(result.get("truncated"))
            self.assertEqual(result.get("scan_limit"), MAX_SCAN_LINES)
            self.assertEqual(result["total"], 0)
        finally:
            big.unlink()

    def test_no_truncation_flag_for_small_files(self):
        """Normal-sized searches must not advertise truncation."""
        result = self.searcher.search(
            str(self.log_file), query="ERROR", use_regex=False
        )
        self.assertNotIn("truncated", result)
