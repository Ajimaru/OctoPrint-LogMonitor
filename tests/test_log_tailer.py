# -*- coding: utf-8 -*-
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

    def _callback(self, line: str):
        """Callback function to capture received log lines."""
        self.received_lines.append(line)

    def test_start_stop(self):
        """Test starting and stopping the tailer."""
        tailer = LogTailer(
            str(self.log_file),
            self._callback,
            poll_interval=0.1
        )

        # Start tailer
        self.assertTrue(tailer.start())
        self.assertTrue(tailer.is_running())

        # Stop tailer
        self.assertTrue(tailer.stop())
        self.assertFalse(tailer.is_running())

    def test_tail_new_lines(self):
        """Test that new lines are captured."""
        # Write initial content
        self.log_file.write_text(
            "2024-01-01 10:00:00,000 - test - INFO - Initial\n"
        )

        tailer = LogTailer(
            str(self.log_file),
            self._callback,
            poll_interval=0.1
        )

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

        tailer = LogTailer(
            str(self.log_file),
            self._callback,
            poll_interval=0.1
        )

        # Get last 2 lines
        last_lines = tailer.get_last_n_lines(2)
        self.assertEqual(len(last_lines), 2)
        # get_last_n_lines returns parsed dicts
        self.assertIn("Line3", last_lines[0]["message"])
        self.assertIn("Line4", last_lines[1]["message"])

        # Get more lines than exist
        all_lines = tailer.get_last_n_lines(10)
        self.assertEqual(len(all_lines), 4)

    def test_file_rotation(self):
        """Test handling of log file rotation."""
        tailer = LogTailer(
            str(self.log_file),
            self._callback,
            poll_interval=0.1
        )

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
            "/nonexistent/path/file.log",
            self._callback,
            poll_interval=0.1
        )

        # Should fail to start
        self.assertFalse(tailer.start())
        self.assertFalse(tailer.is_running())

    def test_double_start(self):
        """Test that starting already running tailer returns False."""
        tailer = LogTailer(
            str(self.log_file),
            self._callback,
            poll_interval=0.1
        )

        self.assertTrue(tailer.start())
        self.assertFalse(tailer.start())  # Second start should fail
        tailer.stop()


if __name__ == "__main__":
    unittest.main()
