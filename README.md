<!-- markdownlint-disable MD041 MD033 -->
<p align="center">
  <img src="assets/img/logmonitor.svg" alt="OctoPrint Log Monitor Logo" width="96" />
</p>
<h1 align="center">OctoPrint‑LogMonitor</h1>
<!-- markdownlint-enable MD041 MD033 -->

[![License](https://img.shields.io/github/license/Ajimaru/OctoPrint-LogMonitor)](https://github.com/Ajimaru/OctoPrint-LogMonitor/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://python.org)
[![OctoPrint](https://img.shields.io/badge/OctoPrint-1.10.0%2B-blue.svg)](https://octoprint.org)
[![Latest Release](https://img.shields.io/github/v/release/Ajimaru/OctoPrint-LogMonitor?sort=semver)](https://github.com/Ajimaru/OctoPrint-LogMonitor/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Ajimaru/OctoPrint-LogMonitor/total.svg)](https://github.com/Ajimaru/OctoPrint-LogMonitor/releases)
[![Made with Love](https://img.shields.io/badge/made_with-❤️-ff69b4)](https://github.com/Ajimaru/OctoPrint-LogMonitor)

### Live log streaming and searching for OctoPrint with severity alerting in the navbar and sidebar

<!-- markdownlint-disable MD033-->
<img src="assets/img/main_screen.png" alt="OctoPrint Log Monitor Main Screen" width="666" />
<!-- markdownlint-enable MD033-->

## Highlights

- 🔴 **Live Log Streaming** - Real-time log monitoring with tail-like behavior
- 🔍 **Full-Text Search** - Search through log files with pagination
- ⚠️ **Severity Alerts** - Visual indicators in Navbar and Sidebar for ERROR/CRITICAL events
- 🎨 **Syntax Highlighting** - Color-coded severity levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- 🔧 **Configurable** - Customize trigger levels, polling intervals, and display options
- 📊 **Multiple Log Files** - Support for all OctoPrint log files
- 🎯 **Smart Filtering** - Filter by severity level and free text in real-time
- 📈 **Alert History** - View recent alerts with timestamps and messages
- 📥 **Log Download** - Download log files directly from the plugin tab
- 🧪 **Advanced Search** - Optional regex and case-sensitive search modes
- 📤 **Export Results** - Export filtered/search results for offline analysis
- 🔀 **Multi-Stream API** - Backend endpoints for parallel streaming of multiple logs
- 🛡️ **Secure** - Path traversal protection, input validation, and rate limiting

## Installation

### Via Plugin Manager (Recommended)

1. Open OctoPrint web interface
2. Navigate to **Settings** → **Plugin Manager**
3. Click **Get More...**
4. Click **Install from URL** and enter: `https://github.com/Ajimaru/OctoPrint-LogMonitor/releases/latest/download/OctoPrint-LogMonitor-latest.zip`

5. Click **Install**
6. Restart OctoPrint

### Manual Installation

<!-- markdownlint-disable MD033 -->
<details>
<summary>Manual pip install</summary>

`pip install https://github.com/Ajimaru/OctoPrint-LogMonitor/releases/latest/download/OctoPrint-LogMonitor-latest.zip`

The `releases/latest` URL always points to the newest stable release.

</details>
<!-- markdownlint-enable MD033 -->

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

- **Poll Interval** - How often to check for new log entries (default: 5s)
- **Max Stream Lines** - Maximum number of lines in buffer (default: 500)
- **Auto-scroll** - Automatically scroll to bottom (default: enabled)

### Search Settings

- **Results per Page** - Number of search results per page (default: 50)
- **Regex Search** - Optional regular expression search mode
- **Case-Sensitive Search** - Toggle exact case matching for queries

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

When a log entry matches configured trigger severities (default: WARNING/ERROR/CRITICAL):

- A badge appears in the Navbar (if enabled)
- The Sidebar widget updates (if enabled)
- Click the badge/widget to open the Log Monitor tab and reset alerts

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines and instructions.

Please also follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

AGPLv3 - See [LICENSE](LICENSE) for details.

## Support

- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/Ajimaru/OctoPrint-LogMonitor/issues)
- 💬 **Discussion**: [GitHub Discussions](https://github.com/Ajimaru/OctoPrint-LogMonitor/discussions)

Note: For logs and troubleshooting, enable "debug logging" in the plugin settings.

## Credits

- **Development**: Built following [OctoPrint Plugin Guidelines](https://docs.octoprint.org/en/main/plugins/index.html)
- **Contributors**: See [AUTHORS.md](AUTHORS.md)

## 100% Badge Coverage

Summary: this project exposes many status and quality badges (CI, linting, coverage, releases, maintenance, etc.). The full badge set is available below; click to expand for details.

<!-- markdownlint-disable MD033 -->
<details>
<summary>Show all badges</summary>

### 🏗️ 1. Build & Test Status

[![CI](https://github.com/Ajimaru/OctoPrint-LogMonitor/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Ajimaru/OctoPrint-LogMonitor/actions/workflows/ci.yml?query=branch%3Amain)
[![i18n](https://github.com/Ajimaru/OctoPrint-LogMonitor/actions/workflows/i18n.yml/badge.svg?branch=main)](https://github.com/Ajimaru/OctoPrint-LogMonitor/actions/workflows/i18n.yml?query=branch%3Amain)
[![Lint](https://github.com/Ajimaru/OctoPrint-LogMonitor/actions/workflows/lint.yml/badge.svg?branch=main)](https://github.com/Ajimaru/OctoPrint-LogMonitor/actions/workflows/lint.yml?query=branch%3Amain)
[![Docs workflow](https://github.com/Ajimaru/OctoPrint-LogMonitor/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/Ajimaru/OctoPrint-LogMonitor/actions/workflows/docs.yml?query=branch%3Amain)
[![Bandit SARIF](https://github.com/Ajimaru/OctoPrint-LogMonitor/actions/workflows/bandit-sarif.yml/badge.svg?branch=main)](https://github.com/Ajimaru/OctoPrint-LogMonitor/actions/workflows/bandit-sarif.yml?query=branch%3Amain)

### 🧪 2. Code Quality & Formatting

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336)](https://pycqa.github.io/isort/)
[![Code style: prettier](https://img.shields.io/badge/code_style-prettier-ff69b4.svg)](https://github.com/prettier/prettier)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://pre-commit.com/)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/1b946ed41ef2479fa1eb254e6eea9fb0)](https://app.codacy.com/gh/Ajimaru/OctoPrint-LogMonitor/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)
[![Coverage](https://codecov.io/gh/Ajimaru/OctoPrint-LogMonitor/graph/badge.svg?branch=main)](https://codecov.io/gh/Ajimaru/OctoPrint-LogMonitor)
[![Pylint Score](https://img.shields.io/badge/pylint-10.0-green.svg)](https://www.pylint.org/)
[![Bandit Security](https://img.shields.io/badge/bandit-security-green.svg)](https://bandit.readthedocs.io/en/latest/)
[![Depfu](https://badges.depfu.com/badges/b1bd984976a5ccb7ac298737eabe686f/status.svg)](https://depfu.com)
[![Known Vulnerabilities](https://snyk.io/test/github/Ajimaru/OctoPrint-LogMonitor/badge.svg)](https://snyk.io/test/github/Ajimaru/OctoPrint-LogMonitor)

### 🔄 3. CI/CD & Release

[![SemVer](https://img.shields.io/badge/semver-2.0.0-blue)](https://semver.org/)
[![Release Date](https://img.shields.io/github/release-date/Ajimaru/OctoPrint-LogMonitor)](https://github.com/Ajimaru/OctoPrint-LogMonitor/releases)
[![Latest Release](https://img.shields.io/github/v/release/Ajimaru/OctoPrint-LogMonitor?sort=semver)](https://github.com/Ajimaru/OctoPrint-LogMonitor/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Ajimaru/OctoPrint-LogMonitor/total.svg)](https://github.com/Ajimaru/OctoPrint-LogMonitor/releases)
[![Pre‑Release](https://img.shields.io/github/v/release/Ajimaru/OctoPrint-LogMonitor?include_prereleases&label=pre-release)](https://github.com/Ajimaru/OctoPrint-LogMonitor/releases)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://python.org)
[![OctoPrint](https://img.shields.io/badge/OctoPrint-1.10.0%2B-blue.svg)](https://octoprint.org)
[![Maintenance](https://img.shields.io/maintenance/yes/2026)](https://github.com/Ajimaru/OctoPrint-LogMonitor/graphs/commit-activity)

### 📊 4. Repository Activity

[![Open Issues](https://img.shields.io/github/issues/Ajimaru/OctoPrint-LogMonitor)](https://github.com/Ajimaru/OctoPrint-LogMonitor/issues?q=is%3Aissue%20state%3Aopen)
[![Closed Issues](https://img.shields.io/github/issues-closed-raw/Ajimaru/OctoPrint-LogMonitor)](https://github.com/Ajimaru/OctoPrint-LogMonitor/issues?q=is%3Aissue%20state%3Aclosed)
[![Open PRs](https://img.shields.io/github/issues-pr/Ajimaru/OctoPrint-LogMonitor)](https://github.com/Ajimaru/OctoPrint-LogMonitor/pulls?q=is%3Apr+is%3Aopen)
[![Closed PRs](https://img.shields.io/github/issues-pr-closed/Ajimaru/OctoPrint-LogMonitor)](https://github.com/Ajimaru/OctoPrint-LogMonitor/pulls?q=is%3Apr+is%3Aclosed)
[![Last Commit](https://img.shields.io/github/last-commit/Ajimaru/OctoPrint-LogMonitor)](https://github.com/Ajimaru/OctoPrint-LogMonitor/commits/main)
[![Commit Activity (year)](https://img.shields.io/github/commit-activity/y/Ajimaru/OctoPrint-LogMonitor)](https://github.com/Ajimaru/OctoPrint-LogMonitor/graphs/commit-activity)
[![Contributors](https://img.shields.io/github/contributors/Ajimaru/OctoPrint-LogMonitor)](https://github.com/Ajimaru/OctoPrint-LogMonitor/graphs/contributors)

### 🧾 5. Metadata

![Code Size](https://img.shields.io/github/languages/code-size/Ajimaru/OctoPrint-LogMonitor)
[![Security](https://img.shields.io/badge/security-policy-blue)](https://github.com/Ajimaru/OctoPrint-LogMonitor/blob/main/SECURITY.md)
[![Snyk](https://img.shields.io/badge/security-snyk-blueviolet)](https://app.snyk.io)
![Languages Count](https://img.shields.io/github/languages/count/Ajimaru/OctoPrint-LogMonitor)
![Top Language](https://img.shields.io/github/languages/top/Ajimaru/OctoPrint-LogMonitor)
[![License](https://img.shields.io/github/license/Ajimaru/OctoPrint-LogMonitor)](https://github.com/Ajimaru/OctoPrint-LogMonitor/blob/main/LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/Ajimaru/OctoPrint-LogMonitor/pulls)

</details>
<!-- markdownlint-enable MD033 -->

---

![Stars](https://img.shields.io/github/stars/Ajimaru/OctoPrint-LogMonitor?style=social) ![Forks](https://img.shields.io/github/forks/Ajimaru/OctoPrint-LogMonitor?style=social) ![Watchers](https://img.shields.io/github/watchers/Ajimaru/OctoPrint-LogMonitor?style=social)

**Like this plugin?** ⭐ Star the repo and share it with the OctoPrint community!
