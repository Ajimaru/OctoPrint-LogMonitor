# Configuration Reference

All settings live under **OctoPrint Settings → Plugins → Log Monitor**.
Values outside the allowed range are clamped automatically when saved.

## Display

| Setting        | Default | Description                                      |
| -------------- | ------- | ------------------------------------------------ |
| `show_navbar`  | `true`  | Show the alert badge in the OctoPrint navbar.    |
| `show_sidebar` | `true`  | Show the status widget in the OctoPrint sidebar. |

## Streaming

| Setting                  | Default         | Range     | Description                                                                 |
| ------------------------ | --------------- | --------- | --------------------------------------------------------------------------- |
| `default_log_file`       | `octoprint.log` | —         | Log file preselected in the tab and used for auto-start.                    |
| `stream_poll_interval_s` | `5`             | 1–60 s    | How often the tailer polls for new lines and batches are flushed to the UI. |
| `max_stream_lines`       | `500`           | 100–10000 | Maximum lines kept in the live view buffer.                                 |
| `auto_scroll`            | `true`          | —         | Scroll to the newest line automatically.                                    |
| `auto_start_streaming`   | `false`         | —         | Start streaming `default_log_file` when OctoPrint starts.                   |

## Search

| Setting                | Default | Range  | Description                                        |
| ---------------------- | ------- | ------ | -------------------------------------------------- |
| `search_page_size`     | `50`    | 10–500 | Results per page.                                  |
| `regex_search_enabled` | `false` | —      | Allow regular-expression queries in the search UI. |

## Alerts

| Setting                 | Default                          | Range  | Description                                                                |
| ----------------------- | -------------------------------- | ------ | -------------------------------------------------------------------------- |
| `alerts_enabled`        | `true`                           | —      | Master switch for severity alerting.                                       |
| `severity_triggers`     | `["WARNING","ERROR","CRITICAL"]` | —      | Levels that raise an alert.                                                |
| `alerts_monitor_mode`   | `selected`                       | —      | `all` monitors every `.log` file; `selected` only `alerts_monitored_logs`. |
| `alerts_monitored_logs` | `["octoprint.log"]`              | —      | Files watched by the background alert monitor (mode `selected`).           |
| `alert_history_enabled` | `true`                           | —      | Keep a history of triggered alerts.                                        |
| `max_alert_history`     | `100`                            | 10–500 | Maximum stored history entries.                                            |
| `enable_notifications`  | `false`                          | —      | Show a toast notification for each alert.                                  |

The alert monitor runs independently of the live-stream view: alerts are
raised even while the Log Monitor tab is closed.

## Privacy & Debugging

| Setting            | Default | Description                                                                                             |
| ------------------ | ------- | ------------------------------------------------------------------------------------------------------- |
| `mask_log_content` | `false` | Mask API keys, passwords, tokens, and e-mail addresses in streamed lines before they reach the browser. |
| `debug_mode`       | `false` | Enable verbose plugin logging and the debug endpoints (frontend event log, test entries).               |

## Built-in limits

These are hard limits enforced by the backend regardless of settings:

- Log files larger than **1 GiB** are rejected for search and streaming.
- Search requests are rate limited to **10 per minute per client**.
- At most **20 files** per multi-stream request.
- Search `limit` parameter caps at **1000**; alert-history `limit` at **500**.
