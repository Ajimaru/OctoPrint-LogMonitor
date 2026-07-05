"""Tests for the shared log_parser module."""

import unittest

from octoprint_logmonitor.log_parser import parse_line


class TestParseLine(unittest.TestCase):
    """Test cases for log_parser.parse_line."""

    def test_parse_standard_line(self):
        """Standard OctoPrint format parses all fields."""
        parsed = parse_line(
            "2024-01-01 10:00:00,123 - octoprint.server - INFO - Started\n"
        )

        self.assertEqual(parsed["timestamp"], "2024-01-01 10:00:00,123")
        self.assertEqual(parsed["logger"], "octoprint.server")
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["message"], "Started")

    def test_parse_standard_line_without_milliseconds(self):
        """Timestamps without milliseconds are accepted."""
        parsed = parse_line(
            "2024-01-01 10:00:00 - octoprint.server - ERROR - Boom"
        )

        self.assertEqual(parsed["timestamp"], "2024-01-01 10:00:00")
        self.assertEqual(parsed["level"], "ERROR")

    def test_parse_hyphenated_logger_name(self):
        """Logger names containing hyphens parse correctly."""
        parsed = parse_line(
            "2024-01-01 10:00:00,123 - octoprint.plugins.my-plugin"
            " - WARNING - Something odd"
        )

        self.assertEqual(parsed["logger"], "octoprint.plugins.my-plugin")
        self.assertEqual(parsed["level"], "WARNING")
        self.assertEqual(parsed["message"], "Something odd")

    def test_parse_simple_serial_line_infers_level(self):
        """Simple serial format infers severity from message keywords."""
        parsed = parse_line(
            "2024-01-01 10:00:00,123 - Recv: Error:checksum mismatch"
        )

        self.assertEqual(parsed["logger"], "serial.log")
        self.assertEqual(parsed["level"], "ERROR")

    def test_parse_compact_line(self):
        """Compact format without ' - ' separators parses correctly."""
        parsed = parse_line(
            "2024-01-01 10:00:00,123WARNING octoprint.plugins.x Watch out"
        )

        self.assertEqual(parsed["level"], "WARNING")
        self.assertEqual(parsed["logger"], "octoprint.plugins.x")
        self.assertEqual(parsed["message"], "Watch out")

    def test_parse_serial_io_line(self):
        """Virtual printer serial I/O lines keep their direction marker."""
        parsed = parse_line("2024-01-01 10:00:00,123 >>> M105")

        self.assertEqual(parsed["logger"], "serial.log")
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["message"], ">>> M105")

    def test_parse_unknown_line(self):
        """Unparsable lines fall back to UNKNOWN with raw message."""
        parsed = parse_line("random text without timestamp")

        self.assertEqual(parsed["level"], "UNKNOWN")
        self.assertEqual(parsed["timestamp"], "")
        self.assertEqual(parsed["logger"], "")
        self.assertEqual(parsed["message"], "random text without timestamp")

    def test_parse_normalizes_tabs(self):
        """Tabs are normalised to four spaces in raw and message."""
        parsed = parse_line(
            "2024-01-01 10:00:00,123 - test - INFO - col1\tcol2\n"
        )

        self.assertNotIn("\t", parsed["raw"])
        self.assertNotIn("\t", parsed["message"])
        self.assertIn("col1    col2", parsed["message"])


if __name__ == "__main__":
    unittest.main()
