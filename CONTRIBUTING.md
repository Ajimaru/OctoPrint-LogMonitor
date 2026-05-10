# Contributing to OctoPrint Log Monitor

Keep contributions small, testable, and easy to review. Bug reports, docs, translations, tests, and code changes are all welcome.

## Code of Conduct

Participation in this project is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to Contribute

### Report a Bug

Before opening an issue, check the [existing issues](https://github.com/Ajimaru/OctoPrint-LogMonitor/issues). Useful bug reports include:

- a short description of the problem
- steps to reproduce
- expected behavior and actual behavior
- OctoPrint version and plugin version
- relevant logs or a systeminfo bundle

### Suggest a Feature

Open a [feature request](https://github.com/Ajimaru/OctoPrint-LogMonitor/issues) and describe:

- the problem to solve
- the proposed behavior
- alternatives or constraints

### Submit Code

1. Fork the repository.
2. Create a branch from the branch you want to target.
3. Make the change in focused commits.
4. Add or update tests and docs when needed.
5. Add a short entry to `CHANGELOG.md` under `[Unreleased]`.
6. Open a pull request with a clear summary.

## Local Setup

Requirements:

- Python 3.9+
- a local OctoPrint environment for manual testing

Recommended setup:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .[develop]
pip install OctoPrint
```

## Common Commands

Run tests:

```bash
pytest
```

Build distributions:

```bash
python -m build --sdist --wheel
```

Translation workflow with Task:

```bash
task babel-extract
task babel-update
task babel-compile
```

Run OctoPrint in safe mode when manually testing plugin behavior:

```bash
octoprint serve --safe
```

## Project Expectations

- Keep Python code consistent with existing style in `octoprint_logmonitor/`.
- Add tests for new behavior and regression tests for bug fixes.
- Keep security in mind: validate paths and user input, and do not expose internal error details.
- Update documentation when UI, API, or setup behavior changes.

## Pull Requests

Before opening a PR, check that:

- tests pass locally
- docs are updated if behavior changed
- `CHANGELOG.md` contains an `[Unreleased]` entry
- no unrelated files are included
- commit messages are clear and focused

If possible, keep each PR to one concern.

## Authors

Contributors are listed in [AUTHORS.md](AUTHORS.md). To add yourself, append a new line in one of these formats:

```text
- Name <email>
- Name (@github-handle)
```

## License

By contributing, you agree that your work is licensed under [AGPL-3.0-or-later](LICENSE).
