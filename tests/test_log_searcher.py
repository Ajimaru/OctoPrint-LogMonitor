# -*- coding: utf-8 -*-
"""
Tests for LogSearcher class.
"""
import os
import tempfile
import unittest
from pathlib import Path

from octoprint_logmonitor.log_searcher import LogSearcher


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
            limit=100
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
            limit=100
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
            use_regex=True
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
            limit=100
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
            limit=100
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
            limit=3
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
            limit=3
        )

        self.assertEqual(len(result_page2["results"]), 3)

        # Results should be different (different timestamps)
        self.assertNotEqual(
            result_page1["results"][0]["timestamp"],
            result_page2["results"][0]["timestamp"]
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
            limit=10
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
            use_regex=True
        )

        # Should return error
        self.assertIn("error", result)

    def test_empty_file(self):
        """Test searching in empty file."""
        empty_file = Path(self.temp_dir) / "empty.log"
        empty_file.touch()

        result = self.searcher.search(
            filepath=str(empty_file),
            query="test",
            levels=None,
            offset=0,
            limit=10
        )

        self.assertEqual(result["total"], 0)
        self.assertEqual(len(result["results"]), 0)

        empty_file.unlink()


if __name__ == "__main__":
    unittest.main()
