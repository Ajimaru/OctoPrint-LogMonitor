# Troubleshooting

## The file dropdown is empty

- The plugin only lists regular files ending in `.log` inside OctoPrint's
  log folder (usually `~/.octoprint/logs`).
- Check that the OctoPrint user can read that folder.

## Streaming shows no new lines

- The tailer starts at the **end** of the file: only lines written after
  the stream starts appear (plus up to 100 initial context lines).
- New lines are delivered in batches once per poll interval
  (`stream_poll_interval_s`, default 5 s) — short delays are expected.
- Rotated and truncated log files are picked up automatically; if a stream
  ever looks stuck, stop and restart it.

## Search returns an error

| Status | Meaning                            | Fix                                             |
| ------ | ---------------------------------- | ----------------------------------------------- |
| `400`  | Invalid filename, level, or paging | Check query parameters.                         |
| `403`  | File outside the log folder        | Only plain filenames in the log folder work.    |
| `404`  | File does not exist                | Refresh the file list.                          |
| `413`  | File larger than 1 GiB             | Rotate/trim the log file.                       |
| `429`  | More than 10 searches per minute   | Wait a moment; the limit is per client address. |

## Alerts do not appear

- Check `alerts_enabled` and that the level is listed in
  `severity_triggers` (defaults: WARNING, ERROR, CRITICAL).
- In mode `selected`, only files in `alerts_monitored_logs` are watched —
  the **Alert monitor status** panel in the plugin settings shows which
  files are currently active.
- Alert toasts additionally require `enable_notifications`.

## Getting more information

1. Enable **debug mode** in the plugin settings.
2. Use **Write test entries** in the settings to generate one log entry
   per severity and verify the whole pipeline.
3. Check `octoprint.log` for entries from `octoprint.plugins.logmonitor` —
   including `[SECURITY]` entries for rejected filenames or rate limits.

Still stuck? Open a
[GitHub issue](https://github.com/Ajimaru/OctoPrint-LogMonitor/issues)
with your OctoPrint version, plugin version, and relevant log excerpts.
