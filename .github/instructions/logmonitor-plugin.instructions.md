description: Development guidelines for implementing the OctoPrint Log Monitor plugin
applyTo: 
  - '**/*.py'
  - '**/*.js'
  - '**/*.jinja2'
  - '**/*.css'
  - 'setup.py'

# OctoPrint Log Monitor Plugin - Development Instructions

## Overview

This plugin provides live log streaming and searching capabilities for OctoPrint with severity-based alerting in the Navbar and Sidebar.

**Implementation Plan:** See [.ideas/plugin-implementation-plan.md](../../.ideas/plugin-implementation-plan.md) for the complete development TODO list.

## Core Principles

### Architecture
- Use OctoPrint's plugin system with proper mixin inheritance
- Implement background threading for log tailing
- Use WebSocket for real-time log streaming
- Implement REST API for search and control endpoints
- Follow OctoPrint's conventions for templates, assets, and settings

### Code Organization
```
octoprint_logmonitor/
├── __init__.py           # Main plugin class with all mixins
├── log_tailer.py         # Background thread for tailing log files
├── log_searcher.py       # Search logic with pagination
├── static/
│   ├── js/logmonitor.js  # KnockoutJS ViewModel
│   └── css/logmonitor.css
└── templates/
    ├── logmonitor_tab.jinja2
    ├── logmonitor_settings.jinja2
    ├── logmonitor_navbar.jinja2
    └── logmonitor_sidebar.jinja2
```

## Implementation Guidelines

### When working on Python backend code:
1. **Always use type hints** for function parameters and return values
2. **Implement proper thread safety** using `threading.Lock()` for shared state
3. **Handle file operations safely:**
   - Use `encoding="utf-8", errors="replace"` for log file reads
   - Validate file paths to prevent path traversal attacks
   - Only allow access to OctoPrint's log directory
4. **Parse log lines into structured format:**
   ```python
   {
       "timestamp": "2026-02-19 12:00:00,000",
       "logger": "octoprint.server",
       "level": "ERROR",
       "message": "Something went wrong",
       "raw": "original full log line"
   }
   ```
5. **Implement graceful shutdown** in `on_shutdown()` callback
6. **Log all errors** but never let background threads crash silently

### When working on frontend (JavaScript/KnockoutJS):
1. **Use KnockoutJS observables** for reactive state management
2. **Register ViewModel** with OctoPrint using `OCTOPRINT_VIEWMODELS`
3. **Handle WebSocket messages** via `OctoPrint.onDataUpdaterPluginMessage`
4. **Implement auto-scroll logic** with manual scroll detection
5. **Use severity color coding:**
   - DEBUG → gray
   - INFO → white/default
   - WARNING → orange/yellow
   - ERROR → red
   - CRITICAL → bold red
6. **Throttle UI updates** when receiving high-frequency log streams

### When working on templates (Jinja2):
1. **Use OctoPrint's template hooks** for Navbar and Sidebar integration
2. **Make Navbar/Sidebar visibility** configurable via settings
3. **Implement clickable badges** that navigate to the plugin tab
4. **Support both light and dark themes**

### API Endpoints Design:
```python
GET  /api/plugin/logmonitor/files          # List available log files
GET  /api/plugin/logmonitor/search         # Search with pagination
POST /api/plugin/logmonitor/stream/start   # Start/switch log streaming
POST /api/plugin/logmonitor/stream/stop    # Stop streaming
POST /api/plugin/logmonitor/alerts/reset   # Reset alert counters
```

### Settings Schema:
```python
{
    "show_navbar": True,
    "show_sidebar": True,
    "severity_triggers": ["WARNING", "ERROR", "CRITICAL"],
    "default_log_file": "octoprint.log",
    "stream_poll_interval_ms": 500,
    "max_stream_lines": 1000,
    "search_page_size": 50,
    "auto_scroll": True
}
```

## Security Requirements

- ✅ **Validate all file paths** to prevent directory traversal
- ✅ **Require API key authentication** for all endpoints
- ✅ **Sanitize user inputs** in search queries
- ✅ **Limit payload sizes** to prevent DoS
- ✅ **Only access files** within OctoPrint's log directory

## Performance Guidelines

- ✅ **Stream large files** line-by-line (never load entire file into memory)
- ✅ **Implement max line buffer** in frontend (e.g., 1000 lines)
- ✅ **Use background threads** for file operations
- ✅ **Throttle WebSocket pushes** to avoid overwhelming clients
- ✅ **Implement pagination** for search results

## Testing Requirements

Before committing code, ensure:
1. **Unit tests** exist for LogTailer, LogSearcher, and severity parsing
2. **Integration tests** cover all API endpoints
3. **Security tests** verify path traversal is blocked
4. **Manual testing** confirms:
   - Navbar badge appears on severity triggers
   - Sidebar widget updates correctly
   - Live stream auto-scrolls properly
   - Search pagination works
   - Settings save/load correctly

## Common Patterns

### Log Tailing Pattern:
```python
class LogTailer:
    def __init__(self, filepath, callback, poll_interval=0.5):
        self._file = open(filepath, 'r', encoding='utf-8', errors='replace')
        self._file.seek(0, 2)  # Seek to EOF
        self._callback = callback
        self._stop_flag = threading.Event()
        
    def run(self):
        while not self._stop_flag.is_set():
            line = self._file.readline()
            if line:
                self._callback(self._parse_line(line))
            else:
                time.sleep(self._poll_interval)
```

### Severity Parsing Pattern:
```python
import re

SEVERITY_PATTERN = re.compile(
    r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - '
    r'([^-]+) - '
    r'(DEBUG|INFO|WARNING|ERROR|CRITICAL) - '
    r'(.+)'
)

def parse_log_line(line: str) -> dict:
    match = SEVERITY_PATTERN.match(line)
    if match:
        return {
            "timestamp": match.group(1),
            "logger": match.group(2).strip(),
            "level": match.group(3),
            "message": match.group(4),
            "raw": line
        }
    return {"raw": line, "level": "UNKNOWN"}
```

## Reference Links

- **Full Implementation Plan:** [.ideas/plugin-implementation-plan.md](../../.ideas/plugin-implementation-plan.md)
- **OctoPrint Plugin Tutorial:** https://docs.octoprint.org/en/master/plugins/gettingstarted.html
- **OctoPrint Plugin Mixins:** https://docs.octoprint.org/en/master/plugins/mixins.html
- **KnockoutJS Documentation:** https://knockoutjs.com/documentation/introduction.html

## Notes

- This plugin requires OctoPrint >= 1.10.0+
- Python >= 3.8 required
- License: AGPLv3
- Follow OctoPrint's coding standards and conventions
- Use semantic versioning for releases
