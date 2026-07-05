# REST API Reference

All endpoints are served under the plugin blueprint:

```text
<octoprint-base>/plugin/logmonitor
```

Requests go through OctoPrint's normal session authentication and CSRF
protection — call them from the OctoPrint web UI context or with a valid
API key/session. Filenames are validated on every endpoint: only plain
`.log` filenames inside OctoPrint's log folder are accepted (no path
components, no hidden files).

## Log files

### `GET /files`

List available log files.

```json
{
  "files": [
    { "name": "octoprint.log", "size": 123456, "modified": 1719999999.0 }
  ]
}
```

### `GET /download/<filename>`

Download a log file as attachment.
Errors: `400` invalid filename, `403` outside log folder, `404` not found.

## Search

### `GET /search`

Search a log file with pagination.

| Parameter        | Default            | Description                                                 |
| ---------------- | ------------------ | ----------------------------------------------------------- |
| `file`           | `default_log_file` | Log filename.                                               |
| `query`          | `""`               | Free-text or regex query.                                   |
| `levels`         | all                | Repeatable severity filter (`levels=ERROR&levels=WARNING`). |
| `offset`         | `0`                | Matches to skip.                                            |
| `limit`          | `search_page_size` | Max results (hard cap 1000).                                |
| `case_sensitive` | `false`            | Exact-case matching.                                        |
| `use_regex`      | `false`            | Treat `query` as a regular expression.                      |

```json
{ "results": [], "total": 0, "offset": 0, "limit": 50 }
```

`total` counts matches until scanning stopped: the backend stops early once
the requested page plus one look-ahead match is complete, so treat it as
"at least this many".

Errors: `400` bad parameters, `403` denied, `404` unknown file,
`413` file larger than 1 GiB, `429` rate limit (10 requests/minute/client).

### `POST /export`

Export search results (the client sends the results back).

```json
{
  "results": [
    { "timestamp": "…", "logger": "…", "level": "…", "message": "…" }
  ],
  "format": "csv"
}
```

`format` is `csv` or `txt`. Returns the file as attachment.
Errors: `400` invalid format or more than 1000 entries.

## Live streaming

Streamed lines are pushed over OctoPrint's plugin WebSocket as batched
messages (see [Push messages](#push-messages)).

### `POST /stream/start`

Start (or switch) the single-file UI stream. Body: `{ "file": "octoprint.log" }`
(defaults to `default_log_file`). Responds with up to 100 initial lines:

```json
{ "status": "started", "file": "octoprint.log", "initial_lines": [] }
```

### `POST /stream/stop`

Stop the single-file stream. Returns `{"status": "stopped"}` or
`{"status": "not_running"}`.

### `POST /stream/multi/start`

Start streaming several files at once (max 20). Body:
`{ "files": ["octoprint.log", "serial.log"] }`.

```json
{ "status": "multi_started", "started": [], "failed": [], "total_active": 2 }
```

Lines from multi-streams carry a `_source_file` field.

### `POST /stream/multi/stop`

Stop specific streams or all of them. Body:
`{ "files": ["serial.log"] }` or `{ "stop_all": true }`.

### `GET /multi-stream`

List currently active multi-stream files.

## Alerts

### `POST /alerts/reset`

Reset the per-severity alert counters.

### `GET /alert-history?limit=100`

Return recent alert entries (newest last, `limit` caps at 500).

### `POST /alert-history/clear`

Clear the alert history.

### `GET /alerts/monitor/status`

Show the background alert monitor configuration and which files are
actively watched.

## Debug (require `debug_mode`)

### `POST /debug/frontend`

Write a frontend debug event into the OctoPrint server log.
Body: `{ "message": "…", "payload": {} }`.

### `POST /debug/test-entries`

Write one test log entry per severity (including `UNKNOWN`) so alert
handling can be verified end to end.

## Push messages

The plugin sends these messages via
`OctoPrint.coreui.viewmodels`/`onDataUpdaterPluginMessage` (plugin id
`logmonitor`):

| `type`           | Payload                                                                                                    |
| ---------------- | ---------------------------------------------------------------------------------------------------------- |
| `log_lines`      | `data`: array of parsed lines (`timestamp`, `logger`, `level`, `message`, `raw`, optional `_source_file`). |
| `severity_alert` | `level`, `count`, `message`, `notification_enabled`, `source_file`.                                        |
