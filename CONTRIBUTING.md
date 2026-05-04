# Contributing to OctoPrint Log Monitor

Thank you for your interest in contributing to OctoPrint Log Monitor! We welcome contributions of all kinds: bug reports, feature requests, documentation improvements, and code contributions.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Coding Conventions](#coding-conventions)
- [Testing Guidelines](#testing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Issue Templates](#issue-templates)

---

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

---

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the [existing issues](https://github.com/Ajimaru/OctoPrint-LogMonitor/issues) to avoid duplicates. When creating a bug report, use the **Bug Report** template and include:

- A clear and descriptive title
- Steps to reproduce the issue
- Expected vs. actual behavior
- OctoPrint version and plugin version
- A systeminfo bundle (generated after the bug occurs)
- Debug logs with `octoprint.plugins.logmonitor` set to DEBUG level

### Suggesting Features

Feature requests are tracked as [GitHub issues](https://github.com/Ajimaru/OctoPrint-LogMonitor/issues). Use the **Feature Request** template and include:

- A clear description of the problem this feature would solve
- A detailed description of the proposed solution
- Any alternative solutions you've considered
- Additional context (mockups, examples, etc.)

### Contributing Code

We love pull requests! Here's how to contribute code:

1. **Fork** the repository and create a new branch from `main`
2. **Make your changes** following our coding conventions
3. **Add or update tests** as needed
4. **Update documentation** (README, docstrings, etc.)
5. **Add an entry** to `CHANGELOG.md` under `[Unreleased]`
6. **Submit a pull request** using our PR template

---

## Development Setup

### Prerequisites

- Python 3.9 or higher
- OctoPrint development environment
- Git

### Local Setup

1. **Clone your fork:**

   ```bash
   git clone https://github.com/YOUR_USERNAME/OctoPrint-LogMonitor.git
   cd OctoPrint-LogMonitor
   ```

2. **Create a virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install in development mode:**

   ```bash
   pip install -e ".[dev]"
   ```

   This installs the plugin in editable mode along with development dependencies (pytest, linting tools, etc.).

4. **Install OctoPrint** (if not already installed):

   ```bash
   pip install OctoPrint
   ```

5. **Run OctoPrint in safe mode** for testing:

   ```bash
   octoprint serve --safe
   ```

   Then navigate to `http://localhost:5000` to access the web interface.

### Project Structure

```files
OctoPrint-LogMonitor/
├── octoprint_logmonitor/    # Plugin source code
│   ├── __init__.py           # Main plugin class
│   ├── log_tailer.py         # Log tailing logic
│   ├── log_searcher.py       # Search functionality
│   ├── security.py           # Security utilities
│   ├── static/               # CSS and JavaScript
│   └── templates/            # Jinja2 templates
├── tests/                    # Test suite
│   ├── test_log_tailer.py
│   ├── test_log_searcher.py
│   └── test_integration_api.py
├── extras/                   # Extra files (issue templates, etc.)
├── README.md
├── CONTRIBUTING.md           # This file
├── CHANGELOG.md
├── LICENSE
└── setup.py
```

---

## Coding Conventions

We follow standard Python best practices:

### Style Guide

- **PEP 8** for Python code style
- **Maximum line length:** 100 characters (not strict, but preferred)
- **Indentation:** 4 spaces (no tabs)

### Code Organization

- **Imports:** Group imports in this order:
  1. Standard library imports
  2. Third-party imports (OctoPrint, Flask, etc.)
  3. Local application imports

  Separate each group with a blank line.

- **Type Hints:** Use type hints for all public functions and methods (Python 3.7+ compatible syntax):

  ```python
  from typing import Dict, List, Optional, Any

  def search_logs(
      self,
      filepath: str,
      query: str = "",
      levels: Optional[List[str]] = None
  ) -> Dict[str, Any]:
      ...
  ```

- **Docstrings:** All public classes, methods, and functions must have docstrings in **Google style**:

  ```python
  def my_function(arg1: str, arg2: int) -> bool:
      """
      Brief one-line description.

      Longer description if needed, explaining the purpose and behavior
      in more detail.

      Args:
          arg1: Description of arg1
          arg2: Description of arg2

      Returns:
          Description of return value

      Raises:
          ValueError: When input is invalid
      """
      ...
  ```

### Naming Conventions

- **Variables and functions:** `snake_case`
- **Classes:** `PascalCase`
- **Constants:** `UPPER_SNAKE_CASE`
- **Private members:** Prefix with single underscore `_internal_method`

### Security Best Practices

- **Never expose internal exception details** to API responses
- **Validate all user inputs** (file paths, query parameters, JSON payloads)
- **Use `security.py` utilities** for path validation, rate limiting, and input sanitization
- **Log security events** using `_log_security_event()` for audit purposes
- **Avoid hardcoded secrets** or credentials in code

---

## Testing Guidelines

### Running Tests

Run the full test suite with:

```bash
pytest
```

Run tests with coverage report:

```bash
pytest --cov=octoprint_logmonitor --cov-report=html
```

Run specific test file:

```bash
pytest tests/test_log_searcher.py
```

### Writing Tests

- **All new features** must include tests
- **Bug fixes** should include a regression test
- **Test file naming:** `test_<module_name>.py`
- **Test function naming:** `test_<functionality>_<scenario>`

Example:

```python
def test_search_with_valid_query_returns_results():
    """Test that search returns results when query matches log entries."""
    searcher = LogSearcher()
    result = searcher.search(
        filepath="test_log.log",
        query="ERROR",
        limit=10
    )
    assert result["total"] > 0
    assert len(result["results"]) <= 10
```

### Linting and Static Analysis

Before submitting a PR, run:

```bash
# Check code style
flake8 octoprint_logmonitor/

# Linting (optional but recommended)
pylint octoprint_logmonitor/

# Type checking (if mypy is installed)
mypy octoprint_logmonitor/

# Security checks
bandit -r octoprint_logmonitor/
```

Fix any issues reported before submitting your PR.

---

## Pull Request Process

### Branch Naming

Use descriptive branch names:

- `feature/add-log-export` — for new features
- `bugfix/fix-search-pagination` — for bug fixes
- `docs/update-readme` — for documentation updates
- `refactor/improve-security` — for refactoring
- `security/fix-path-traversal` — for security fixes

### Commit Messages

Follow **Conventional Commits** format:

```code
<type>(<scope>): <short description>

<optional longer description>

<optional footer>
```

**Types:**

- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation changes
- `refactor:` — Code refactoring
- `test:` — Adding or updating tests
- `security:` — Security-related changes
- `chore:` — Maintenance tasks

**Examples:**

```text
feat(search): add regex search mode

Added optional regex mode for log search with case-sensitive toggle.

Closes #42
```

```text
fix(tailer): handle file rotation correctly

Fixed issue where log rotation caused streaming to stop.

Fixes #58
```

### Pull Request Checklist

Before submitting, ensure:

- [ ] Code follows the project's coding conventions
- [ ] All tests pass (`pytest`)
- [ ] New tests added for new features or bug fixes
- [ ] Documentation updated (README, docstrings, etc.)
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] No unnecessary files committed (check `.gitignore`)
- [ ] Commits are clear and follow Conventional Commits format
- [ ] PR description explains what was changed and why

### Review Process

1. A maintainer will review your PR within 1-2 weeks
2. Address any requested changes
3. Once approved, a maintainer will merge your PR
4. Your contribution will be included in the next release!

---

## Issue Templates

When creating issues, please use the appropriate template:

- **Bug Report** (`.github/ISSUE_TEMPLATE/bug_report.yml`) — for reporting bugs
- **Feature Request** (`.github/ISSUE_TEMPLATE/feature_request.yml`) — for suggesting features

Template sources are also kept in `extras/github/` for reference.

---

## Contributors and Authors

We keep a list of authors and contributors in [AUTHORS.md](AUTHORS.md).

To add yourself, append a new line using one of the formats below:

```text
- Name <email>
- Name (@github-handle)
```

---

## License

By contributing to OctoPrint Log Monitor, you agree that your contributions will be licensed under the [AGPL-3.0-or-later](LICENSE) license.

---

## Questions?

If you have questions about contributing, feel free to:

- Open a [discussion](https://github.com/Ajimaru/OctoPrint-LogMonitor/discussions)
- Ask in an existing issue
- Reach out to the maintainers

Thank you for contributing! 🎉
