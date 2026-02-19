# OctoPrint Log Monitor

Live log streaming and searching for OctoPrint with severity alerting.

## Features

- 🔴 **Live Log Streaming** - Real-time log monitoring with tail-like behavior
- 🔍 **Full-Text Search** - Search through log files with pagination
- ⚠️ **Severity Alerts** - Visual indicators in Navbar and Sidebar for ERROR/CRITICAL events
- 🎨 **Syntax Highlighting** - Color-coded severity levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- 🔧 **Configurable** - Customize trigger levels, polling intervals, and display options
- 📊 **Multiple Log Files** - Support for all OctoPrint log files
- 🎯 **Smart Filtering** - Filter by severity level and free text in real-time

## Screenshots

_Coming soon_

## Installation

Install via the bundled [Plugin Manager](https://docs.octoprint.org/en/main/bundledplugins/pluginmanager.html)
or manually using this URL:

    https://github.com/Ajimaru/OctoPrint-LogMonitor/archive/main.zip

### Manual Installation

    ```bash
    pip install "https://github.com/Ajimaru/OctoPrint-LogMonitor/archive/main.zip"
    ```

## Configuration

Access plugin settings via OctoPrint Settings → Plugins → Log Monitor

### Display Settings

- **Show in Navbar** - Display alert badge in navigation bar
- **Show in Sidebar** - Display status widget in sidebar

### Severity Triggers

Configure which severity levels trigger alerts:

- DEBUG
- INFO
- WARNING _(default)_
- ERROR _(default)_
- CRITICAL _(default)_

### Streaming Settings

- **Poll Interval** - How often to check for new log entries (default: 500ms)
- **Max Stream Lines** - Maximum number of lines in buffer (default: 1000)
- **Auto-scroll** - Automatically scroll to bottom (default: enabled)

### Search Settings

- **Results per Page** - Number of search results per page (default: 50)

## Usage

### Live Streaming

1. Navigate to the **Log Monitor** tab
2. Select a log file from the dropdown
3. Click **Start Streaming**
4. Watch logs in real-time with color-coded severity levels

**Controls:**

- Use checkboxes to filter by severity level
- Enter text in filter box for real-time client-side filtering
- Click **Clear** to remove all displayed lines
- Toggle **Auto-scroll** to control scroll behavior

### Searching Logs

1. Scroll down to the **Search Logs** section
2. Enter your search query
3. Select severity levels to include
4. Click **Search**
5. Navigate results with pagination controls

### Alerts

When a log entry matches configured trigger severities:

- A badge appears in the Navbar (if enabled)
- The Sidebar widget updates (if enabled)
- Click the badge/widget to open the Log Monitor tab and reset alerts

## Technical Details

### Architecture

- **Backend:** Python with threading for log tailing
- **Frontend:** KnockoutJS for reactive UI
- **Communication:** WebSocket for real-time streaming + REST API for search
- **Security:** Path traversal protection, API key authentication

### Requirements

- OctoPrint >= 1.7.0
- Python >= 3.7

## Development

### Project Structure

    ```filesystem
    octoprint_logmonitor/
    ├── __init__.py              # Main plugin class
    ├── log_tailer.py            # Background log tailing thread
    ├── log_searcher.py          # Log search with pagination
    ├── static/
    │   ├── css/
    │   │   └── logmonitor.css   # Plugin styling
    │   └── js/
    │       └── logmonitor.js    # KnockoutJS ViewModel
    └── templates/
        ├── logmonitor_tab.jinja2     # Main UI tab
        ├── logmonitor_navbar.jinja2   # Navbar badge
        ├── logmonitor_sidebar.jinja2  # Sidebar widget
        └── logmonitor_settings.jinja2 # Settings panel
    ```

### Testing

    ```bash
    # Install development dependencies
    pip install -e ".[dev]"

    # Run tests
    pytest

    # Run linting
    flake8 octoprint_logmonitor
    ```

### Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes and add tests
4. Run tests and linting
5. Commit your changes: `git commit -am 'Add new feature'`
6. Push to the branch: `git push origin feature/my-feature`
7. Submit a pull request

## Support

If you encounter any issues or have feature requests:

- Open an issue on [GitHub](https://github.com/Ajimaru/OctoPrint-LogMonitor/issues)
- Check existing issues for solutions

## License

This project is licensed under the GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later).
See [LICENSE](LICENSE) file for details.

## Credits

Built with:

- [OctoPrint](https://octoprint.org/) - The snappy web interface for your 3D printer
- [KnockoutJS](https://knockoutjs.com/) - MVVM framework
- [Bootstrap](https://getbootstrap.com/) - UI components

---

**Made with ❤️ for the OctoPrint community**
