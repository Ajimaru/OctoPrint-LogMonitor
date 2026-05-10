"""
Tests for LogTailer class.
"""

import os
import tempfile
import time
import unittest
from pathlib import Path

from octoprint_logmonitor.log_tailer import LogTailer


class TestLogTailer(unittest.TestCase):
    """Test cases for LogTailer functionality."""

    # pylint: disable=protected-access

    def setUp(self):
        """Create a temporary log file for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = Path(self.temp_dir) / "test.log"
        self.log_file.touch()
        self.received_lines = []

    def tearDown(self):
        """Clean up temporary files."""
        if self.log_file.exists():
            self.log_file.unlink()
        os.rmdir(self.temp_dir)

    def _callback(self, line: dict) -> None:
        """Callback function to capture received log lines."""
        self.received_lines.append(line)

    def test_start_stop(self):
        """Test starting and stopping the tailer."""
        tailer = LogTailer(str(self.log_file), self._callback, poll_interval=0.1)

        # Start tailer
        self.assertTrue(tailer.start())
        self.assertTrue(tailer.is_running())

        # Stop tailer
        self.assertTrue(tailer.stop())
        self.assertFalse(tailer.is_running())

    def test_tail_new_lines(self):
        """Test that new lines are captured."""
        # Write initial content
        self.log_file.write_text("2024-01-01 10:00:00,000 - test - INFO - Initial\n")

        tailer = LogTailer(str(self.log_file), self._callback, poll_interval=0.1)

        tailer.start()
        time.sleep(0.2)  # Allow tailer to start

        # Append new lines
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write("2024-01-01 10:00:01,000 - test - INFO - Line1\n")
            f.write("2024-01-01 10:00:02,000 - test - ERROR - Line2\n")
            f.flush()

        # Wait for tailer to process
        time.sleep(0.3)

        tailer.stop()

        # Check received lines (should not include initial content)
        # Callback receives parsed dicts, not strings
        self.assertGreaterEqual(len(self.received_lines), 2)
        # Check message field in parsed dict
        self.assertIn("Line1", self.received_lines[-2]["message"])
        self.assertIn("Line2", self.received_lines[-1]["message"])

    def test_get_last_lines(self):
        """Test retrieving last N lines from file."""
        # Write test content
        lines = [
            "2024-01-01 10:00:00,000 - test - INFO - Line1\n",
            "2024-01-01 10:00:01,000 - test - WARNING - Line2\n",
            "2024-01-01 10:00:02,000 - test - ERROR - Line3\n",
            "2024-01-01 10:00:03,000 - test - INFO - Line4\n",
        ]
        self.log_file.write_text("".join(lines))

        tailer = LogTailer(str(self.log_file), self._callback, poll_interval=0.1)

        # Get last 2 lines
        last_lines = tailer.get_last_n_lines(2)
        self.assertEqual(len(last_lines), 2)
        # get_last_n_lines returns parsed dicts
        self.assertIn("Line3", last_lines[0]["message"])
        self.assertIn("Line4", last_lines[1]["message"])

        # Get more lines than exist
        all_lines = tailer.get_last_n_lines(10)
        self.assertEqual(len(all_lines), 4)

    def test_get_last_lines_empty_file(self):
        """Empty file should return an empty list."""
        tailer = LogTailer(str(self.log_file), self._callback, poll_interval=0.1)

        last_lines = tailer.get_last_n_lines(5)

        self.assertEqual(last_lines, [])

    def test_file_rotation(self):
        """Test handling of log file rotation."""
        tailer = LogTailer(str(self.log_file), self._callback, poll_interval=0.1)

        # Write initial content
        self.log_file.write_text(
            "2024-01-01 10:00:00,000 - test - INFO - Before rotation\n"
        )

        tailer.start()
        time.sleep(0.2)

        # Simulate rotation: delete and recreate file
        self.log_file.unlink()
        self.log_file.touch()
        self.log_file.write_text(
            "2024-01-01 10:00:01,000 - test - INFO - After rotation\n"
        )

        # Wait for rotation detection
        time.sleep(0.5)

        tailer.stop()

        # Should have received the line after rotation
        self.assertGreater(len(self.received_lines), 0)

    def test_invalid_file(self):
        """Test behavior with non-existent file."""
        tailer = LogTailer(
            "/nonexistent/path/file.log", self._callback, poll_interval=0.1
        )

        # Should fail to start
        self.assertFalse(tailer.start())
        self.assertFalse(tailer.is_running())

    def test_double_start(self):
        """Test that starting already running tailer returns False."""
        tailer = LogTailer(str(self.log_file), self._callback, poll_interval=0.1)

        self.assertTrue(tailer.start())
        self.assertFalse(tailer.start())  # Second start should fail
        tailer.stop()

    def test_parse_simple_serial_log_line(self):
        """Serial-style lines without explicit logger/level should still parse."""
        tailer = LogTailer(str(self.log_file), self._callback, poll_interval=0.1)
        line = "2026-05-01 19:58:57,717 - serial.log is currently not enabled\n"

        parsed = tailer._parse_line(line)

        self.assertEqual(parsed["timestamp"], "2026-05-01 19:58:57,717")
        self.assertEqual(parsed["logger"], "serial.log")
        self.assertEqual(parsed["level"], "INFO")
        self.assertIn("serial.log is currently not enabled", parsed["message"])

    def test_parse_line_normalizes_tabs(self):
        """Tab characters should be normalized to spaces to avoid visual jumps."""
        tailer = LogTailer(str(self.log_file), self._callback, poll_interval=0.1)
        line = "2026-05-01 20:00:00,000 - test - INFO - A\tB\tC\n"

        parsed = tailer._parse_line(line)

        self.assertNotIn("\t", parsed["message"])
        self.assertNotIn("\t", parsed["raw"])

    def test_parse_serial_io_arrow_line(self):
        """Virtual printer serial lines with >>>/<<< should not be UNKNOWN."""
        tailer = LogTailer(str(self.log_file), self._callback, poll_interval=0.1)
        out_line = "2026-05-01 20:03:06,887 >>> wait\n"
        in_line = "2026-05-01 20:03:06,888 <<< ok\n"

        parsed_out = tailer._parse_line(out_line)
        parsed_in = tailer._parse_line(in_line)

        self.assertEqual(parsed_out["level"], "INFO")
        self.assertEqual(parsed_out["logger"], "serial.log")
        self.assertEqual(parsed_out["message"], ">>> wait")

        self.assertEqual(parsed_in["level"], "INFO")
        self.assertEqual(parsed_in["logger"], "serial.log")
        self.assertEqual(parsed_in["message"], "<<< ok")

    def test_parse_compact_warning_line(self):
        """Compact OctoPrint warning lines should still map to WARNING level."""
        tailer = LogTailer(str(self.log_file), self._callback, poll_interval=0.1)
        line = (
            "2026-05-03 22:20:17,441WARNING octoprint.plugins.logmonitor "
            "The templates of this plugin are currently not being autoescaped\n"
        )

        parsed = tailer._parse_line(line)

        self.assertEqual(parsed["timestamp"], "2026-05-03 22:20:17,441")
        self.assertEqual(parsed["level"], "WARNING")
        self.assertEqual(parsed["logger"], "octoprint.plugins.logmonitor")
        self.assertIn("autoescaped", parsed["message"])


if __name__ == "__main__":
    unittest.main()
