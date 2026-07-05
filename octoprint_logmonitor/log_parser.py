"""Shared log-line parsing for the Log Monitor plugin.

Single source of truth for the log formats understood by both the live
tailer (:mod:`.log_tailer`) and the search backend (:mod:`.log_searcher`),
so that streaming and searching always classify lines identically.

Supported formats (tried in order):

1. Standard OctoPrint format::

       YYYY-MM-DD HH:MM:SS[,ms] - LOGGER - LEVEL - MESSAGE

2. Simple serial-log format (level inferred from message keywords)::

       YYYY-MM-DD HH:MM:SS[,ms] - MESSAGE

3. Compact format without ``" - "`` separators::

       YYYY-MM-DD HH:MM:SS[,ms]LEVEL LOGGER MESSAGE

4. Serial I/O format from the virtual printer::

       YYYY-MM-DD HH:MM:SS[,ms] >>> MESSAGE

Anything else is returned with level ``UNKNOWN`` and the raw line as the
message.
"""

import re
from typing import Any

#: Timestamp prefix shared by all supported formats.
_TIMESTAMP = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d{3})?"

#: Standard OctoPrint log format:
#: ``YYYY-MM-DD HH:MM:SS[,ms] - LOGGER - LEVEL - MESSAGE``.
#: The logger group is non-greedy so hyphenated logger names
#: (e.g. ``octoprint.plugins.my-plugin``) parse correctly.
LOG_PATTERN = re.compile(
    rf"^({_TIMESTAMP})\s+-\s+"
    r"(.+?)\s+-\s+"
    r"(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+-\s+"
    r"(.+)$"
)

#: Serial log often uses: ``YYYY-MM-DD HH:MM:SS[,ms] - MESSAGE``.
SIMPLE_LOG_PATTERN = re.compile(rf"^({_TIMESTAMP})\s+-\s+(.+)$")

#: Compact lines without the usual ``" - "`` separators:
#: ``YYYY-MM-DD HH:MM:SS[,ms]LEVEL LOGGER MESSAGE``.
COMPACT_LOG_PATTERN = re.compile(
    rf"^({_TIMESTAMP})"
    r"\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
    r"([A-Za-z0-9_.:-]+)\s+(.+)$"
)

#: Virtual printer serial I/O lines:
#: ``YYYY-MM-DD HH:MM:SS[,ms] >>> MESSAGE``.
SERIAL_IO_PATTERN = re.compile(rf"^({_TIMESTAMP})\s+(>>>|<<<)\s+(.+)$")

#: Keywords used to infer a severity level from free-form serial-log
#: messages, checked in order of decreasing severity.
_INFERRED_LEVELS = ("CRITICAL", "ERROR", "WARNING", "DEBUG")


def parse_line(line: str) -> dict[str, Any]:
    """Parse a raw log line into a structured dictionary.

    Args:
        line: Raw log line (trailing newline is stripped, tabs are
            normalised to four spaces).

    Returns:
        Dictionary with the keys ``timestamp``, ``logger``, ``level``,
        ``message`` and ``raw``.  Lines that match no known format get
        level ``UNKNOWN`` with empty timestamp/logger fields.
    """
    line = line.rstrip("\n\r")
    raw_line = line.replace("\t", "    ")

    match = LOG_PATTERN.match(raw_line)
    if match:
        return {
            "timestamp": match.group(1),
            "logger": match.group(2).strip(),
            "level": match.group(3),
            "message": match.group(4),
            "raw": raw_line,
        }

    simple_match = SIMPLE_LOG_PATTERN.match(raw_line)
    if simple_match:
        message = simple_match.group(2).strip()
        level = "INFO"
        upper_message = message.upper()
        for candidate in _INFERRED_LEVELS:
            if candidate in upper_message:
                level = candidate
                break

        return {
            "timestamp": simple_match.group(1),
            "logger": "serial.log",
            "level": level,
            "message": message,
            "raw": raw_line,
        }

    compact_match = COMPACT_LOG_PATTERN.match(raw_line)
    if compact_match:
        return {
            "timestamp": compact_match.group(1),
            "logger": compact_match.group(3).strip(),
            "level": compact_match.group(2),
            "message": compact_match.group(4),
            "raw": raw_line,
        }

    serial_match = SERIAL_IO_PATTERN.match(raw_line)
    if serial_match:
        direction = serial_match.group(2)
        message = serial_match.group(3).strip()
        return {
            "timestamp": serial_match.group(1),
            "logger": "serial.log",
            "level": "INFO",
            "message": f"{direction} {message}",
            "raw": raw_line,
        }

    # Line doesn't match any known format, return as-is
    return {
        "timestamp": "",
        "logger": "",
        "level": "UNKNOWN",
        "message": raw_line,
        "raw": raw_line,
    }
