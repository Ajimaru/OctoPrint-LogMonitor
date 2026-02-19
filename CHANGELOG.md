# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Initial Release (2026-02-19)

### Added

#### Core Features

- **Live Log Streaming**: Real-time log monitoring with tail-like behavior
- **Full-Text Search**: Search through log files with pagination and filtering
- **Severity Alerting**: Visual indicators in Navbar and Sidebar for ERROR/CRITICAL events
- **Severity Filtering**: Filter logs by DEBUG, INFO, WARNING, ERROR, CRITICAL levels
- **Free-Text Filtering**: Real-time client-side filtering of streamed logs
- **Syntax Highlighting**: Color-coded severity levels for easy visual scanning
- **Multiple Log Files**: Support for all OctoPrint log files (octoprint.log, plugin_*.log)
- **Multi-File Streaming**: Stream multiple log files simultaneously with merged view
- **Regex Search Mode**: Optional regex search toggle in the UI
- **Export Results**: Export search results to CSV or TXT
- **Log Download**: Download log files directly from the plugin tab
- **Alert History**: View alert history with timestamps and messages
- **Notifications**: Browser notifications for severity alerts
- **Auto-Start Streaming**: Optional auto-start on page load

#### Backend Components

- `LogTailer`: Background thread-based log file tailing with file rotation support
- `LogSearcher`: Memory-efficient log search with pagination and context lines
- RESTful API endpoints for file listing, searching, and streaming control
- WebSocket messaging for real-time log streaming and severity alerts
- Thread-safe alert counting and tracking
- Path traversal protection and input validation

#### Frontend Components

- Main plugin tab with live stream panel and search panel
- Navbar badge with severity alert indicators
- Sidebar widget showing alert status and counts
- KnockoutJS ViewModel for reactive UI updates
- CSS styling with dark/light theme support
- Responsive design supporting Bootstrap UI

#### Configuration

- Configurable Navbar and Sidebar visibility
- Customizable severity trigger levels
- Adjustable polling interval (500ms default)
- Configurable max stream buffer size (1000 lines default)
- Auto-scroll toggle for streamed logs
- Configurable search results per page (50 default)
- Optional alert history tracking and size limits
- Optional client-side log masking for sensitive data

#### Testing

- Unit tests for `LogTailer` (file tailing, rotation, graceful shutdown)
- Unit tests for `LogSearcher` (text search, regex, severity filtering, pagination)
- Unit tests for severity parsing (format validation, error handling)
- Integration tests for REST API endpoints (security validation included)
- Manual browser testing checklist for UI behaviors

#### Documentation

- Comprehensive README with features, installation, and usage guide
- Inline code comments for non-obvious logic
- Full docstrings for public classes and methods
- CHANGELOG documentation (this file)
- AGPL-3.0-or-later license file
- CONTRIBUTING, CODE_OF_CONDUCT, AUTHORS, SECURITY documentation
- CODEOWNERS and PR template for review workflow

### Technical Details

- **Language**: Python 3.7+
- **Framework**: OctoPrint Plugin API
- **Frontend**: KnockoutJS + jQuery + Bootstrap
- **Threading**: Python threading for background log tailing
- **Security**: API key authentication, path traversal prevention, encoding error handling
- **Performance**: Line-by-line log reading (no full file loading), efficient pagination

### Known Limitations

- Screenshots not yet included in README (documentation task)
- Test coverage is still in progress (security.py and plugin core need more tests)
- Log file watching for new file creation not implemented (optional)

---

## Future Roadmap

### Planned Features

- [ ] Plugin Manager compatibility badge
- [ ] Internationalization (i18n) support
- [ ] OctoPrint Plugin Repository submission
