"""
Log Tailer Module

Provides background thread-based log file tailing functionality.
Similar to 'tail -f' behavior for live log streaming.
"""

import os
import re
import threading
import time
from typing import Any, Callable, Optional


class LogTailer:
    """
    Background thread that continuously monitors a log file for new lines.

    Features:
    - Thread-safe start/stop
    - Handles file rotation
    - Parses OctoPrint log format
    - Calls callback for each new line
    """

    # OctoPrint log format: YYYY-MM-DD HH:MM:SS[,ms] - LOGGER - LEVEL - MESSAGE
    LOG_PATTERN = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d{3})?)\s+-\s+"
        r"([^\-]+)\s+-\s+"
        r"(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+-\s+"
        r"(.+)$"
    )

    def __init__(
        self,
        filepath: str,
        callback: Callable[[dict[str, Any]], None],
        poll_interval: float = 0.5,
        logger: Optional[Any] = None,
    ):
        """
        Initialize the log tailer.

        Args:
            filepath: Path to the log file to tail
            callback: Function to call for each new log line
                     (receives parsed dict)
            poll_interval: Polling interval in seconds (default: 0.5)
            logger: Optional logger instance for debugging
        """
        self._filepath = filepath
        self._callback = callback
        self._poll_interval = poll_interval
        self._logger = logger

        self._file = None
        self._file_inode = None
        self._thread = None
        self._stop_flag = threading.Event()
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> bool:
        """
        Start the log tailer in a background thread.

        Returns:
            True if started successfully, False otherwise
        """
        with self._lock:
            if self._running:
                if self._logger:
                    self._logger.warning("LogTailer already running")
                return False

            if not os.path.exists(self._filepath):
                if self._logger:
                    self._logger.error(f"Log file not found: {self._filepath}")
                return False

            try:
                self._file = open(self._filepath, encoding="utf-8", errors="replace")
                self._file_inode = os.fstat(self._file.fileno()).st_ino

                # Seek to end of file (start tailing from current position)
                self._file.seek(0, 2)  # SEEK_END

                self._stop_flag.clear()
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
                self._running = True

                if self._logger:
                    self._logger.info(f"LogTailer started for {self._filepath}")

                return True

            except Exception as e:
                if self._logger:
                    self._logger.error(f"Failed to start LogTailer: {e}")
                if self._file:
                    self._file.close()
                    self._file = None
                return False

    def stop(self, timeout: float = 5.0) -> bool:
        """
        Stop the log tailer gracefully.

        Args:
            timeout: Maximum time to wait for thread to stop

        Returns:
            True if stopped successfully, False if timeout
        """
        with self._lock:
            if not self._running:
                return True

            self._stop_flag.set()
            self._running = False

        # Wait for thread to stop (outside lock to avoid deadlock)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

            if self._thread.is_alive():
                if self._logger:
                    self._logger.warning("LogTailer thread did not stop gracefully")
                return False

        if self._file:
            try:
                self._file.close()
            except Exception as e:
                if self._logger:
                    self._logger.error(f"Error closing log file: {e}")
            finally:
                self._file = None

        if self._logger:
            self._logger.info("LogTailer stopped")

        return True

    def is_running(self) -> bool:
        """Check if the tailer is currently running."""
        with self._lock:
            return self._running

    def _run(self):
        """Main loop running in background thread."""
        try:
            while not self._stop_flag.is_set():
                # Check for file rotation
                if self._check_rotation():
                    if self._logger:
                        self._logger.info("Log file rotated, reopening")
                    self._reopen_file()

                # Read new lines
                line = self._file.readline()

                if line:
                    # Process the line
                    parsed = self._parse_line(line)
                    try:
                        self._callback(parsed)
                    except Exception as e:
                        if self._logger:
                            self._logger.error(f"Error in callback: {e}")
                else:
                    # No new data, wait before next check
                    time.sleep(self._poll_interval)

        except Exception as e:
            if self._logger:
                self._logger.error(f"Error in LogTailer thread: {e}")
        finally:
            if self._logger:
                self._logger.debug("LogTailer thread exiting")

    def _check_rotation(self) -> bool:
        """
        Check if the log file has been rotated.

        Returns:
            True if rotation detected, False otherwise
        """
        try:
            current_inode = os.stat(self._filepath).st_ino
            return current_inode != self._file_inode
        except OSError:
            return False

    def _reopen_file(self):
        """Reopen the log file after rotation."""
        try:
            if self._file:
                self._file.close()

            self._file = open(self._filepath, encoding="utf-8", errors="replace")
            self._file_inode = os.fstat(self._file.fileno()).st_ino

            # Start from beginning of new file
            self._file.seek(0, 0)

        except Exception as e:
            if self._logger:
                self._logger.error(f"Failed to reopen log file: {e}")

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
        else:
            # Line doesn't match expected format, return as-is
            return {
                "timestamp": "",
                "logger": "",
                "level": "UNKNOWN",
                "message": line,
                "raw": line,
            }

    def get_last_n_lines(self, n: int = 100) -> list:
        """
        Read the last N lines from the log file.

        Args:
            n: Number of lines to read

        Returns:
            List of parsed log line dictionaries
        """
        if not os.path.exists(self._filepath):
            return []

        try:
            with open(self._filepath, encoding="utf-8", errors="replace") as f:
                # Read all lines
                lines = f.readlines()

                # Get last N lines
                last_lines = lines[-n:] if len(lines) > n else lines

                # Parse each line
                return [self._parse_line(line) for line in last_lines]

        except Exception as e:
            if self._logger:
                self._logger.error(f"Error reading last lines: {e}")
            return []
