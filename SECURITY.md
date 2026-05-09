# Security Policy – OctoPrint Log Monitor

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅ Yes    |
| < 0.1   | ❌ No     |

---

## Assumptions & Scope

The OctoPrint Log Monitor plugin reads log files produced by OctoPrint and
streams their content to authenticated users through OctoPrint's existing
web interface. The following security assumptions apply:

- **Authentication is provided by OctoPrint.** All API endpoints exposed by
  this plugin (`/api/plugin/logmonitor/*`) require a valid OctoPrint API key.
  The plugin does not implement its own authentication mechanism.
- **The OctoPrint host is trusted.** The plugin runs with the same OS-level
  privileges as OctoPrint itself. If OctoPrint is compromised, the plugin
  offers no additional isolation.
- **Log files may contain sensitive information.** OctoPrint log files can
  contain passwords, API keys, email addresses, and other personal data.
  Access should be restricted to trusted administrators only. The optional
  **Mask sensitive log content** setting (`mask_log_content`) can redact
  common sensitive patterns (API keys, passwords, emails) before they reach
  the browser, but it is not a substitute for proper access control.

---

## Built-in Security Controls

| Control                       | Details                                                                                                                                                                                                                                               |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Path traversal prevention** | All file names supplied by API callers are validated with `validate_filename()` and `is_safe_path()` before any filesystem access. Absolute paths, `..` components, and symlink escapes are rejected with HTTP 400/403 and logged as security events. |
| **File-size guard**           | Files larger than 1 GiB are rejected to prevent memory exhaustion (HTTP 413).                                                                                                                                                                         |
| **Rate limiting**             | The search endpoint enforces a sliding-window rate limit (10 requests / minute per client IP) to mitigate abuse (HTTP 429).                                                                                                                           |
| **Input validation**          | `offset`, `limit`, severity level strings, and all JSON payloads are validated; bad input returns HTTP 400.                                                                                                                                           |
| **Generic error responses**   | Internal exception messages, stack traces, and file paths are written to OctoPrint's server log only and are never returned to API callers.                                                                                                           |
| **Sensitive data masking**    | When `mask_log_content` is enabled in plugin settings, streamed log lines are scanned for API keys, passwords, Bearer tokens, and email addresses and the values are replaced with `[REDACTED]`.                                                      |
| **Audit logging**             | Path traversal attempts, rate-limit violations, and invalid filename submissions are logged as `[SECURITY]` events in OctoPrint's server log.                                                                                                         |
| **Thread safety**             | Shared state (alert counters, alert history, tailer references) is protected by `threading.Lock()` instances to prevent race conditions.                                                                                                              |

---

## Known Limitations

- **No per-user access control beyond OctoPrint roles.** Any authenticated
  OctoPrint user who can reach the plugin's API can read any log file in
  OctoPrint's log directory.
- **WebSocket transport security depends on your OctoPrint deployment.** If
  OctoPrint is served without TLS (HTTP instead of HTTPS), log content is
  transmitted in plaintext. Use a reverse proxy with TLS termination in
  production.
- **Sensitive data masking is best-effort.** The regex patterns cover common
  cases (passwords, API keys, Bearer tokens, email addresses) but cannot
  detect all possible sensitive values. Do not rely on masking as the sole
  protection for highly confidential log data.

---

## Reporting a Vulnerability

If you believe you have found a security vulnerability in OctoPrint Log
Monitor, please **do not open a public GitHub issue**.

Report vulnerabilities by emailing:

> **<security@ajimaru.dev>** _(replace with the actual contact address)_

Please include:

1. A clear description of the vulnerability and its potential impact.
2. Reproduction steps (version, configuration, request/response details).
3. Any suggested mitigations you may have identified.

We aim to acknowledge reports within **48 hours** and to publish a patched
release within **14 days** for critical issues. We will credit reporters in
the changelog unless they prefer to remain anonymous.

### Scope

In-scope for vulnerability reports:

- Path traversal / arbitrary file read
- Authentication bypass
- Denial of service via resource exhaustion
- Information disclosure (internal paths, stack traces, sensitive data)
- Injection attacks (regex, command, etc.)

Out of scope:

- Vulnerabilities in OctoPrint itself (report to the OctoPrint project)
- Issues that require physical access to the host machine
- Social-engineering attacks

---

## Security Changelog

| Version | Date       | Summary                                                                                                                                                               |
| ------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0.1.0   | 2026-02-19 | Initial release with path traversal protection, rate limiting, input validation, file-size guard, generic error responses, sensitive data masking, and audit logging. |
