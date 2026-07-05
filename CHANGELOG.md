# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
For the detailed history of published versions, see the
[GitHub releases](https://github.com/Ajimaru/OctoPrint-LogMonitor/releases).

## [Unreleased]

### Added

- Shared `log_parser` module: streaming and searching now classify log
  lines identically (search understands serial and compact formats too).
- Copy-truncate log rotation detection: a truncated file no longer stalls
  the live stream.
- Documentation: configuration reference, REST API reference, and
  troubleshooting guide.

### Changed

- Search now streams through log files line by line instead of loading
  them fully into memory; the initial-lines read also uses backward block
  reads. Memory use no longer scales with file size.
- Hyphenated logger names (e.g. `octoprint.plugins.my-plugin`) parse
  correctly.
- `max_alert_history` is now consistently capped at 500 in settings, UI,
  and runtime.

### Fixed

- Batched line delivery now starts reliably for auto-started and
  multi-file streams, and stopping the single-file stream no longer stalls
  active multi-file streams.
- The line buffer is hard-capped so memory stays bounded even if flushing
  stalls; the search rate limiter prunes idle clients automatically.
- `POST /stream/multi/stop` with `stop_all` reports the actual number of
  stopped streams.

## [0.2.3] - 2026-06

- Version 0.2.3: improved log path validation and error handling.

See [GitHub releases](https://github.com/Ajimaru/OctoPrint-LogMonitor/releases)
for earlier versions.
