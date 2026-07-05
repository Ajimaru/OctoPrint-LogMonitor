# Plugin Overview

OctoPrint Log Monitor streams OctoPrint logs live, searches them with
pagination and severity filters, and shows alert badges in the navbar and
sidebar.

## Core features

- Live log streaming (single file from the UI, multiple files via the API)
- Full-text search with severity filters, regex and case-sensitive modes
- Background severity alerting with history, independent of the UI stream
- Log download and search-result export (CSV/TXT)
- Path traversal protection, rate limiting, and optional masking of
  sensitive log content

## How it works

The backend consists of four small modules:

| Module         | Responsibility                                                                                          |
| -------------- | ------------------------------------------------------------------------------------------------------- |
| `log_parser`   | Single source of truth for parsing OctoPrint, serial, and compact log-line formats.                     |
| `log_tailer`   | `tail -f`-style background thread per streamed file; detects rotation and truncation.                   |
| `log_searcher` | Streams through files line by line for search, stats, and exports — memory use is bounded by page size. |
| `security`     | Filename/path validation, file-size guard, rate limiting, sensitive-data masking.                       |

The plugin core (`octoprint_logmonitor/__init__.py`) wires these together:

- **Live stream** — a tailer per streamed file pushes parsed lines into a
  shared buffer, which is flushed to the browser as one batched WebSocket
  message per poll interval.
- **Alert monitor** — separate tailers watch the configured log files and
  raise `severity_alert` messages whenever a line matches the trigger
  levels, even while the Log Monitor tab is closed.
- **REST API** — all routes live under `/plugin/logmonitor`; see the
  [REST API reference](rest-api.md).

## Further reading

- [Configuration reference](configuration.md)
- [REST API reference](rest-api.md)
- [Troubleshooting](troubleshooting.md)
- [Python API](api/python.md)

See the project README for installation notes.
