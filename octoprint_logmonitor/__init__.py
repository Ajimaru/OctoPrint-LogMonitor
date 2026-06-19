"""OctoPrint Log Monitor Plugin.

Provides live log streaming and searching capabilities
with severity-based alerting.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from typing import Any, Literal

import flask
import octoprint.plugin
from octoprint.server.util.flask import no_firstrun_access

from ._version import VERSION as PLUGIN_VERSION
from .log_searcher import LogSearcher
from .log_tailer import LogTailer
from .security import (
    MAX_HISTORY_LIMIT,
    MAX_SEARCH_LIMIT,
    RateLimiter,
    check_file_size,
    is_safe_path,
    mask_sensitive_data,
    validate_filename,
    validate_pagination,
    validate_severity_levels,
)

# pylint: disable=broad-except,global-statement,too-many-lines
# intentional: plugin handlers must not crash OctoPrint


# Error codes returned by ``_resolve_log_path``.
_LogPathErrorCode = Literal["invalid", "denied", "not_found"]

# Maps the error code from ``_resolve_log_path`` to a client-safe
# ``(message, http_status)`` pair.
_LOG_PATH_ERRORS: dict[_LogPathErrorCode, tuple[str, int]] = {
    "invalid": ("Invalid filename", 400),
    "denied": ("Access denied", 403),
    "not_found": ("Log file not found", 404),
}


class LogmonitorPlugin(
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.BlueprintPlugin,
):
    """Main plugin class implementing OctoPrint Log Monitor functionality.

    Features:

    - Live log streaming via WebSocket
    - Full-text log search with severity filtering
    - Navbar and Sidebar indicators for severity alerts
    - Configurable severity triggers
    """

    # OctoPrint-injected attributes (set by plugin framework at runtime)
    _logger: logging.Logger
    _settings: Any
    _plugin_manager: Any
    _identifier: str
    _plugin_version: str

    def __init__(self):
        """Initialize plugin state."""
        super().__init__()
        self._tailer = None
        self._searcher = None
        self._alert_counts = {}
        self._alert_lock = threading.Lock()
        self._alert_history = []  # Store alert history
        # Alert monitor tailers (independent from UI stream)
        self._alert_tailers = {}
        self._active_tailers = {}  # Support multi-file streaming
        # Rate-limit search API: max 10 requests per minute per client
        self._search_rate_limiter = RateLimiter(max_calls=10, period=60.0)
        # Line buffer: collect lines, flush as batch to reduce WebSocket
        # pressure
        self._line_buffer = []
        self._line_buffer_lock = threading.Lock()
        self._flush_timer = None
        self._runtime_settings_lock = threading.Lock()
        self._runtime_alert_settings = {
            "alerts_enabled": True,
            "severity_triggers": ["WARNING", "ERROR", "CRITICAL"],
            "alert_history_enabled": True,
            "max_alert_history": 100,
            "enable_notifications": True,
        }

    # ~~ StartupPlugin mixin

    def on_after_startup(self):
        """Initialize plugin after OctoPrint startup."""
        plugin_version = getattr(self, "_plugin_version", "unknown")
        plugin_id = getattr(self, "_identifier", "logmonitor")
        self._logger.info(
            "Loaded plugin %s: Log Monitor Plugin started (version %s)",
            plugin_id,
            plugin_version,
        )

        self._refresh_runtime_alert_settings()
        self._log_settings_snapshot_if_debug_enabled("Startup")

        # Initialize searcher
        self._searcher = LogSearcher(logger=self._logger)

        # Reset alert counts
        with self._alert_lock:
            self._alert_counts = {
                "DEBUG": 0,
                "INFO": 0,
                "WARNING": 0,
                "ERROR": 0,
                "CRITICAL": 0,
            }

        # Start independent alert monitoring (not tied to UI live streaming)
        self._restart_alert_monitoring()

        # Auto-start streaming if enabled
        if self._settings.get(["auto_start_streaming"]):
            try:
                default_log_file = self._settings.get(["default_log_file"])
                log_dir = self._get_logs_base_folder()
                filepath = os.path.join(log_dir, default_log_file)

                if os.path.exists(filepath):
                    poll_interval = self._get_stream_poll_interval_seconds()
                    self._tailer = LogTailer(
                        filepath=filepath,
                        callback=self._handle_log_line,
                        poll_interval=poll_interval,
                        logger=self._logger,
                    )
                    if self._tailer.start():
                        self._logger.info(
                            f"Auto-started streaming for {default_log_file}"
                        )
                    else:
                        self._logger.warning("Failed to auto-start streaming")
                else:
                    self._logger.warning(
                        f"Default log file not found: {filepath}"
                    )
            except Exception as e:
                self._logger.error(f"Error auto-starting stream: {e}")

    def on_shutdown(self):
        """Clean shutdown of background threads."""
        self._logger.info("Log Monitor Plugin shutting down")

        # Stop main tailer if running
        if self._tailer and self._tailer.is_running():
            self._tailer.stop()
            self._tailer = None

        # Stop all multi-file tailers
        for filename, tailer in self._active_tailers.items():
            try:
                if tailer.is_running():
                    tailer.stop()
            except Exception as e:
                self._logger.error(
                    f"Error stopping tailer for {filename}: {e}"
                )

        self._active_tailers.clear()
        self._stop_alert_monitoring()

    def on_settings_save(self, data):
        """Persist settings and refresh background alert monitoring."""
        if isinstance(data, dict):
            plugins_data = data.get("plugins")
            if isinstance(plugins_data, dict):
                plugin_data = plugins_data.get("logmonitor")
                if isinstance(plugin_data, dict):

                    def clamp_int_setting(key, default, minimum, maximum):
                        raw_value = plugin_data.get(key)
                        if raw_value is None:
                            parsed = default
                        else:
                            try:
                                parsed = int(raw_value)
                            except (TypeError, ValueError):
                                parsed = default
                        plugin_data[key] = min(maximum, max(minimum, parsed))

                    raw_interval_seconds = plugin_data.get(
                        "stream_poll_interval_s"
                    )
                    raw_interval_ms = plugin_data.get(
                        "stream_poll_interval_ms"
                    )

                    # Backward compatibility: convert legacy milliseconds
                    # setting.
                    if (
                        raw_interval_seconds is None
                        and raw_interval_ms is not None
                    ):
                        try:
                            raw_interval_seconds = (
                                float(raw_interval_ms) / 1000.0
                            )
                        except (TypeError, ValueError):
                            raw_interval_seconds = 5.0

                    if raw_interval_seconds is None:
                        interval_seconds = 5
                    else:
                        try:
                            interval_seconds = int(float(raw_interval_seconds))
                        except (TypeError, ValueError):
                            interval_seconds = 5

                    plugin_data["stream_poll_interval_s"] = min(
                        60, max(1, interval_seconds)
                    )
                    plugin_data.pop("stream_poll_interval_ms", None)

                    clamp_int_setting("max_stream_lines", 500, 100, 10000)
                    clamp_int_setting("search_page_size", 50, 10, 500)
                    clamp_int_setting("max_alert_history", 100, 10, 1000)

                    alerts_enabled = plugin_data.get("alerts_enabled")
                    if isinstance(alerts_enabled, str):
                        plugin_data[
                            "alerts_enabled"
                        ] = alerts_enabled.lower() in {
                            "1",
                            "true",
                            "yes",
                            "on",
                        }
                    elif isinstance(alerts_enabled, bool):
                        plugin_data["alerts_enabled"] = alerts_enabled

                    monitor_mode = plugin_data.get("alerts_monitor_mode")
                    if monitor_mode not in {"all", "selected"}:
                        plugin_data["alerts_monitor_mode"] = "selected"

                    raw_logs = plugin_data.get("alerts_monitored_logs")
                    if isinstance(raw_logs, str):
                        raw_logs = [raw_logs]
                    elif not isinstance(raw_logs, list):
                        raw_logs = []

                    cleaned_logs = []
                    seen = set()
                    for item in raw_logs:
                        if not isinstance(item, str):
                            continue
                        name = item.strip()
                        if not name or name in seen:
                            continue
                        if not validate_filename(name):
                            continue
                        cleaned_logs.append(name)
                        seen.add(name)

                    plugin_data["alerts_monitored_logs"] = cleaned_logs

        result = octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self._refresh_runtime_alert_settings()
        self._log_settings_snapshot_if_debug_enabled("Save")
        self._restart_alert_monitoring()
        return result

    # ~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        """Define default plugin settings."""
        return {
            "show_navbar": True,
            "show_sidebar": True,
            "alerts_enabled": True,
            "severity_triggers": ["WARNING", "ERROR", "CRITICAL"],
            "default_log_file": "octoprint.log",
            "stream_poll_interval_s": 5,
            "max_stream_lines": 500,
            "search_page_size": 50,
            "auto_scroll": True,
            "auto_start_streaming": False,
            "enable_notifications": False,
            "regex_search_enabled": False,
            "alert_history_enabled": True,
            "max_alert_history": 100,
            "alerts_monitor_mode": "selected",  # all|selected
            "alerts_monitored_logs": ["octoprint.log"],
            # Mask sensitive data (API keys, passwords, emails) in streamed log
            # lines
            "mask_log_content": False,
            "debug_mode": False,
        }

    # ~~ AssetPlugin mixin

    def get_assets(self):
        """Define asset files to include in the UI."""
        return {
            "js": ["js/logmonitor.js"],
            "css": ["css/logmonitor.css"],
        }

    # ~~ TemplatePlugin mixin

    def get_template_configs(self):
        """Define template configurations for tab, navbar, and sidebar."""
        show_navbar = self._settings.get(["show_navbar"])
        show_sidebar = self._settings.get(["show_sidebar"])

        return [
            {
                "type": "tab",
                "name": "Log Monitor",
                "custom_bindings": True,
            },
            {
                "type": "navbar",
                "custom_bindings": True,
                "data_bind": "visible: showNavbar",
                "styles": [] if show_navbar else ["display: none"],
            },
            {
                "type": "sidebar",
                "name": "Log Monitor",
                "icon": "list-alt",
                "custom_bindings": True,
                "data_bind": "visible: showSidebar",
                "styles_wrapper": [] if show_sidebar else ["display: none"],
            },
            {
                "type": "settings",
                "custom_bindings": False,
            },
        ]

    def get_template_vars(self):
        """Provide additional template variables for rendering settings UI."""
        return {
            "log_files": self._get_available_log_filenames(),
        }

    def is_template_autoescaped(self):  # type: ignore[override]
        """Enable Jinja autoescaping for all plugin templates."""
        return True

    def _get_available_log_filenames(self):
        """Return sorted list of available .log filenames.

        Scans the OctoPrint log folder.
        """
        try:
            log_dir = self._get_logs_base_folder()
            if not os.path.exists(log_dir):
                return []

            files = []
            for filename in os.listdir(log_dir):
                filepath = os.path.join(log_dir, filename)
                if os.path.isfile(filepath) and filename.endswith(".log"):
                    files.append(filename)

            return sorted(files)
        except Exception as e:
            self._logger.error(
                f"Error listing log filenames for template vars: {e}"
            )
            return []

    def _get_stream_poll_interval_seconds(self) -> float:
        """Return stream polling interval in seconds with legacy fallback."""
        value_seconds = self._settings.get(["stream_poll_interval_s"])
        if value_seconds is None:
            value_ms = self._settings.get(["stream_poll_interval_ms"])
            if value_ms is not None:
                try:
                    return min(60.0, max(1.0, float(value_ms) / 1000.0))
                except (TypeError, ValueError):
                    return 5.0
            return 5.0

        try:
            return min(60.0, max(1.0, float(value_seconds)))
        except (TypeError, ValueError):
            return 5.0

    # ~~ BlueprintPlugin mixin

    @octoprint.plugin.BlueprintPlugin.route("/files", methods=["GET"])
    @no_firstrun_access
    def get_log_files(self):
        """Get list of available log files."""
        try:
            log_dir = self._get_logs_base_folder()

            if not os.path.exists(log_dir):
                return flask.jsonify(
                    {"files": [], "error": "Log directory not found"}
                )

            files = []
            for filename in os.listdir(log_dir):
                filepath = os.path.join(log_dir, filename)

                # Only include .log files
                if os.path.isfile(filepath) and filename.endswith(".log"):
                    files.append(
                        {
                            "name": filename,
                            "size": os.path.getsize(filepath),
                            "modified": os.path.getmtime(filepath),
                        }
                    )

            # Sort by name
            files.sort(key=lambda x: x["name"])

            return flask.jsonify({"files": files})

        except Exception as e:
            self._logger.error(f"Error listing log files: {e}")
            return (
                flask.jsonify(
                    {
                        "files": [],
                        "error": "Failed to list log files."
                        " See server log for details.",
                    }
                ),
                500,
            )

    @octoprint.plugin.BlueprintPlugin.route("/search", methods=["GET"])
    @no_firstrun_access
    def search_logs(self):
        """Search logs with pagination and severity filtering."""
        try:
            # --- Rate limiting ---
            client_ip = flask.request.remote_addr or "unknown"
            if not self._search_rate_limiter.is_allowed(client_ip):
                self._log_security_event(
                    "rate_limit_exceeded",
                    f"Search rate limit exceeded for {client_ip}",
                )
                return (
                    flask.jsonify(
                        {"error": "Too many requests. Please slow down."}
                    ),
                    429,
                )

            # --- Parse & validate parameters ---
            filename = flask.request.args.get(
                "file", str(self._settings.get(["default_log_file"]) or "")
            )
            query = flask.request.args.get("query", "")
            raw_levels = flask.request.args.getlist("levels")
            case_sensitive = (
                flask.request.args.get("case_sensitive", "false").lower()
                == "true"
            )
            use_regex = (
                flask.request.args.get("use_regex", "false").lower() == "true"
            )

            # Validate and clamp offset / limit
            try:
                offset = int(flask.request.args.get("offset", 0))
                limit = int(
                    flask.request.args.get(
                        "limit", str(self._settings.get(["search_page_size"]))
                    )
                )
            except (ValueError, TypeError):
                return (
                    flask.jsonify(
                        {"error": "offset and limit must be integers"}
                    ),
                    400,
                )

            valid, err = validate_pagination(offset, limit)
            if not valid:
                return flask.jsonify({"error": err}), 400

            # Validate severity levels
            valid_levels, invalid_levels = validate_severity_levels(raw_levels)
            if invalid_levels:
                return (
                    flask.jsonify(
                        {
                            "error": (
                                "Invalid severity level(s): "
                                f"{', '.join(invalid_levels)}"
                            )
                        }
                    ),
                    400,
                )

            # --- Filename / path validation ---
            filepath, err_code = self._resolve_log_path(filename, "search")
            if filepath is None:
                if err_code is None:
                    return flask.jsonify({"error": "internal error"}), 500
                msg, status = _LOG_PATH_ERRORS[err_code]
                return flask.jsonify({"error": msg}), status

            # --- File-size guard ---
            if not check_file_size(filepath):
                self._logger.warning(
                    f"Search rejected: file too large: {filename}"
                )
                return (
                    flask.jsonify(
                        {"error": "Log file is too large to process"}
                    ),
                    413,
                )

            # --- Perform search ---
            if not self._searcher:
                self._searcher = LogSearcher(logger=self._logger)

            result = self._searcher.search(
                filepath=filepath,
                query=query,
                levels=valid_levels if valid_levels else None,
                offset=offset,
                limit=limit,
                case_sensitive=case_sensitive,
                use_regex=use_regex,
            )

            return flask.jsonify(result)

        except Exception as e:
            self._logger.error(f"Error searching logs: {e}")
            return (
                flask.jsonify(
                    {"error": "Search failed. See server log for details."}
                ),
                500,
            )

    @octoprint.plugin.BlueprintPlugin.route("/stream/start", methods=["POST"])
    @no_firstrun_access
    def start_stream(self):
        """Start or switch log streaming."""
        try:
            data = flask.request.get_json(silent=True) or {}
            filename = data.get(
                "file", self._settings.get(["default_log_file"])
            )

            # --- Filename / path validation ---
            filepath, err_code = self._resolve_log_path(
                filename, "stream/start"
            )
            if filepath is None:
                if err_code is None:
                    return flask.jsonify({"error": "internal error"}), 500
                msg, status = _LOG_PATH_ERRORS[err_code]
                return flask.jsonify({"error": msg}), status

            # --- File-size guard ---
            if not check_file_size(filepath):
                self._logger.warning(
                    f"Stream rejected: file too large: {filename}"
                )
                return (
                    flask.jsonify(
                        {"error": "Log file is too large to stream"}
                    ),
                    413,
                )

            # Stop existing tailer if running
            if self._tailer and self._tailer.is_running():
                self._tailer.stop()

            # Create new tailer
            poll_interval = self._get_stream_poll_interval_seconds()
            self._tailer = LogTailer(
                filepath=filepath,
                callback=self._handle_log_line,
                poll_interval=poll_interval,
                logger=self._logger,
            )

            # Start tailing
            if self._tailer.start():
                # Start batch-flush timer
                if self._flush_timer:
                    self._flush_timer.cancel()
                with self._line_buffer_lock:
                    self._line_buffer.clear()
                self._start_flush_timer()

                # Send initial lines
                initial_lines_count = 100  # Default
                initial_lines = self._tailer.get_last_n_lines(
                    initial_lines_count
                )

                return flask.jsonify(
                    {
                        "status": "started",
                        "file": filename,
                        "initial_lines": initial_lines,
                    }
                )
            else:
                return (
                    flask.jsonify({"error": "Failed to start streaming"}),
                    500,
                )

        except Exception as e:
            self._logger.error(f"Error starting stream: {e}")
            return (
                flask.jsonify(
                    {
                        "error": "Failed to start streaming."
                        " See server log for details."
                    }
                ),
                500,
            )

    @octoprint.plugin.BlueprintPlugin.route("/stream/stop", methods=["POST"])
    @no_firstrun_access
    def stop_stream(self):
        """Stop log streaming."""
        try:
            if self._flush_timer:
                self._flush_timer.cancel()
                self._flush_timer = None
            with self._line_buffer_lock:
                self._line_buffer.clear()
            if self._tailer and self._tailer.is_running():
                self._tailer.stop()
                self._tailer = None
                return flask.jsonify({"status": "stopped"})
            else:
                return flask.jsonify({"status": "not_running"})

        except Exception as e:
            self._logger.error(f"Error stopping stream: {e}")
            return flask.jsonify({"error": "Failed to stop stream"}), 500

    @octoprint.plugin.BlueprintPlugin.route(
        "/stream/multi/start", methods=["POST"]
    )
    @no_firstrun_access
    def start_multi_stream(self):
        """Start streaming multiple log files simultaneously (NEW)."""
        try:
            data = flask.request.get_json(silent=True) or {}
            files = data.get("files", [])

            if not isinstance(files, list) or not files:
                return flask.jsonify({"error": "No files specified"}), 400

            # Hard cap: prevent absurdly large file lists
            if len(files) > 20:
                return (
                    flask.jsonify(
                        {"error": "Too many files specified (max 20)"}
                    ),
                    400,
                )

            started_files = []
            failed_files = []

            for filename in files:
                # Validate filename and path
                filepath, err_code = self._resolve_log_path(
                    filename, "multi-stream"
                )
                if filepath is None:
                    if err_code is None:
                        return flask.jsonify({"error": "internal error"}), 500
                    msg = _LOG_PATH_ERRORS[err_code][0]
                    label = (
                        filename
                        if isinstance(filename, str)
                        else str(filename)
                    )
                    failed_files.append({"file": label, "error": msg})
                    continue

                # File-size guard
                if not check_file_size(filepath):
                    self._logger.warning(
                        f"Multi-stream rejected: file too large: {filename}"
                    )
                    failed_files.append(
                        {
                            "file": filename,
                            "error": "File is too large to stream",
                        }
                    )
                    continue

                # Stop existing tailer for this file if any
                if filename in self._active_tailers:
                    try:
                        self._active_tailers[filename].stop()
                    except Exception as e:  # noqa: BLE001
                        self._logger.debug(
                            "Failed to stop tailer for %s: %s", filename, e
                        )

                # Create new tailer
                poll_interval = self._get_stream_poll_interval_seconds()

                # Wrap callback to add file context
                def make_callback(fname):
                    def callback(line):
                        line["_source_file"] = fname
                        self._handle_log_line(line)

                    return callback

                tailer = LogTailer(
                    filepath=filepath,
                    callback=make_callback(filename),
                    poll_interval=poll_interval,
                    logger=self._logger,
                )

                if tailer.start():
                    self._active_tailers[filename] = tailer
                    started_files.append(filename)
                else:
                    failed_files.append(
                        {"file": filename, "error": "Failed to start"}
                    )

            return flask.jsonify(
                {
                    "status": "multi_started",
                    "started": started_files,
                    "failed": failed_files,
                    "total_active": len(self._active_tailers),
                }
            )

        except Exception as e:
            self._logger.error(f"Error starting multi-stream: {e}")
            return (
                flask.jsonify({"error": "Failed to start multi-stream"}),
                500,
            )

    @octoprint.plugin.BlueprintPlugin.route(
        "/stream/multi/stop", methods=["POST"]
    )
    @no_firstrun_access
    def stop_multi_stream(self):
        """Stop streaming specific log files (NEW)."""
        try:
            data = flask.request.get_json(silent=True) or {}
            files = data.get("files", [])
            stop_all = data.get("stop_all", False)

            # Validate file list type
            if not isinstance(files, list):
                return flask.jsonify({"error": "files must be a list"}), 400

            if stop_all:
                for filename, tailer in list(self._active_tailers.items()):
                    try:
                        tailer.stop()
                        del self._active_tailers[filename]
                    except Exception as e:
                        self._logger.error(f"Error stopping {filename}: {e}")

                return flask.jsonify(
                    {"status": "all_stopped", "total_stopped": len(files)}
                )
            else:
                stopped_files = []
                for filename in files:
                    # Only allow plain string filenames; ignore others silently
                    if not isinstance(filename, str) or not validate_filename(
                        filename
                    ):
                        continue
                    if filename in self._active_tailers:
                        try:
                            self._active_tailers[filename].stop()
                            del self._active_tailers[filename]
                            stopped_files.append(filename)
                        except Exception as e:
                            self._logger.error(
                                f"Error stopping {filename}: {e}"
                            )

                return flask.jsonify(
                    {
                        "status": "multi_stopped",
                        "stopped": stopped_files,
                        "total_remaining": len(self._active_tailers),
                    }
                )

        except Exception as e:
            self._logger.error(f"Error stopping multi-stream: {e}")
            return flask.jsonify({"error": "Failed to stop multi-stream"}), 500

    @octoprint.plugin.BlueprintPlugin.route("/alerts/reset", methods=["POST"])
    @no_firstrun_access
    def reset_alerts(self):
        """Reset severity alert counters."""
        try:
            with self._alert_lock:
                self._alert_counts = {
                    "DEBUG": 0,
                    "INFO": 0,
                    "WARNING": 0,
                    "ERROR": 0,
                    "CRITICAL": 0,
                }

            return flask.jsonify({"status": "reset"})

        except Exception as e:
            self._logger.error(f"Error resetting alerts: {e}")
            return flask.jsonify({"error": "Failed to reset alerts"}), 500

    @octoprint.plugin.BlueprintPlugin.route(
        "/debug/frontend", methods=["POST"]
    )
    @no_firstrun_access
    def frontend_debug_log(self):
        """Write frontend debug events into OctoPrint server logs."""
        try:
            if not self._settings.get(["debug_mode"]):
                return flask.jsonify({"status": "debug_disabled"})

            data = flask.request.get_json(silent=True) or {}

            message = data.get("message", "")
            if not isinstance(message, str):
                message = str(message)
            message = message.strip()[:300]
            if not message:
                message = "Frontend debug event"

            payload = data.get("payload")
            payload_text = ""
            if payload is not None:
                try:
                    payload_text = json.dumps(
                        payload, ensure_ascii=True, default=str
                    )
                except TypeError:
                    payload_text = str(payload)
                payload_text = payload_text[:2000]

            client_ip = flask.request.remote_addr or "unknown"
            if payload_text:
                self._logger.debug(
                    f"[Frontend Debug] {message}"
                    f" | ip={client_ip} | payload={payload_text}"
                )
            else:
                self._logger.debug(
                    f"[Frontend Debug] {message} | ip={client_ip}"
                )

            return flask.jsonify({"status": "logged"})

        except Exception as e:
            self._logger.error(f"Error writing frontend debug log: {e}")
            return flask.jsonify({"error": "Failed to write debug log"}), 500

    @octoprint.plugin.BlueprintPlugin.route(
        "/debug/test-entries", methods=["POST"]
    )
    @no_firstrun_access
    def write_debug_test_entries(self):
        """Write one test entry per severity category into OctoPrint logs."""
        try:
            if not self._settings.get(["debug_mode"]):
                return flask.jsonify({"status": "debug_disabled"})

            entries = [
                ("DEBUG", "Debug test entry"),
                ("INFO", "Info test entry"),
                ("WARNING", "Warning test entry"),
                ("ERROR", "Error test entry"),
                ("CRITICAL", "Critical test entry"),
                ("UNKNOWN", "Unknown test entry"),
            ]

            for level, message in entries:
                prefix = f"[LogMonitor Debug Test] [{level}] "
                if level == "DEBUG":
                    self._logger.debug(prefix + message)
                elif level == "INFO":
                    self._logger.info(prefix + message)
                elif level == "WARNING":
                    self._logger.warning(prefix + message)
                elif level == "ERROR":
                    self._logger.error(prefix + message)
                elif level == "CRITICAL":
                    self._logger.critical(prefix + message)
                else:
                    self._write_unknown_debug_test_log(prefix + message)

                self._record_alert_line(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "logger": self._logger.name,
                        "level": level,
                        "message": prefix + message,
                        "raw": prefix + message,
                        "_source_file": "octoprint.log",
                    },
                    force=True,
                )

            return flask.jsonify({"status": "logged", "entries": len(entries)})

        except Exception as e:
            self._logger.error(f"Error writing debug test entries: {e}")
            return (
                flask.jsonify({"error": "Failed to write debug test entries"}),
                500,
            )

    @octoprint.plugin.BlueprintPlugin.route("/export", methods=["POST"])
    @no_firstrun_access
    def export_results(self):
        """Export search results to CSV or TXT format."""
        try:
            data = flask.request.get_json(silent=True) or {}
            results = data.get("results", [])
            format_type = data.get("format", "csv").lower()

            # Guard against excessively large export payloads
            if (
                not isinstance(results, list)
                or len(results) > MAX_SEARCH_LIMIT
            ):
                return (
                    flask.jsonify(
                        {
                            "error": (
                                "results must be a list of at most "
                                f"{MAX_SEARCH_LIMIT} entries"
                            )
                        }
                    ),
                    400,
                )

            if format_type not in ["csv", "txt"]:
                return flask.jsonify({"error": "Invalid format"}), 400

            if not self._searcher:
                self._searcher = LogSearcher(logger=self._logger)

            if format_type == "csv":
                content = self._searcher.export_to_csv(results)
                filename = "logmonitor_export.csv"
                mimetype = "text/csv"
            else:
                content = self._searcher.export_to_txt(results)
                filename = "logmonitor_export.txt"
                mimetype = "text/plain"

            return flask.Response(
                content,
                mimetype=mimetype,
                headers={
                    "Content-Disposition": (f"attachment;filename={filename}")
                },
            )

        except Exception as e:
            self._logger.error(f"Error exporting results: {e}")
            return flask.jsonify({"error": "Export failed"}), 500

    @octoprint.plugin.BlueprintPlugin.route(
        "/download/<path:filename>", methods=["GET"]
    )
    @no_firstrun_access
    def download_log_file(self, filename):
        """Download a log file directly."""
        try:
            # --- Filename / path validation ---
            if not validate_filename(filename):
                self._log_security_event(
                    "invalid_filename",
                    f"Rejected filename in download: {filename!r}",
                )
                return flask.jsonify({"error": "Invalid filename"}), 400

            log_dir = self._get_logs_base_folder()
            if not is_safe_path(log_dir, filename):
                self._log_security_event(
                    "path_traversal",
                    f"Path traversal attempt in download: {filename!r}",
                )
                return flask.jsonify({"error": "Access denied"}), 403

            filepath = os.path.join(log_dir, filename)

            if not os.path.isfile(filepath):
                return flask.jsonify({"error": "File not found"}), 404

            return flask.send_file(
                filepath, as_attachment=True, download_name=filename
            )

        except Exception as e:
            self._logger.error(f"Error downloading file: {e}")
            return flask.jsonify({"error": "Download failed"}), 500

    @octoprint.plugin.BlueprintPlugin.route("/alert-history", methods=["GET"])
    @no_firstrun_access
    def get_alert_history(self):
        """Get alert history."""
        try:
            try:
                limit = int(flask.request.args.get("limit", 100))
            except (ValueError, TypeError):
                return (
                    flask.jsonify({"error": "limit must be an integer"}),
                    400,
                )

            # Clamp to safe maximum
            limit = min(max(1, limit), MAX_HISTORY_LIMIT)

            with self._alert_lock:
                history = self._alert_history[-limit:]
                total = len(self._alert_history)

            return flask.jsonify({"history": history, "total": total})

        except Exception as e:
            self._logger.error(f"Error getting alert history: {e}")
            return (
                flask.jsonify({"error": "Failed to retrieve alert history"}),
                500,
            )

    @octoprint.plugin.BlueprintPlugin.route(
        "/alert-history/clear", methods=["POST"]
    )
    @no_firstrun_access
    def clear_alert_history(self):
        """Clear alert history."""
        try:
            with self._alert_lock:
                self._alert_history = []

            return flask.jsonify({"status": "cleared"})

        except Exception as e:
            self._logger.error(f"Error clearing alert history: {e}")
            return (
                flask.jsonify({"error": "Failed to clear alert history"}),
                500,
            )

    @octoprint.plugin.BlueprintPlugin.route(
        "/alerts/monitor/status", methods=["GET"]
    )
    @no_firstrun_access
    def get_alert_monitor_status(self):
        """Return current alert-monitor configuration and active files."""
        try:
            configured = self._get_alert_monitor_files()
            return flask.jsonify(
                {
                    "enabled": bool(self._settings.get(["alerts_enabled"])),
                    "mode": self._settings.get(["alerts_monitor_mode"]),
                    "configured_logs": configured,
                    "active_logs": sorted(list(self._alert_tailers.keys())),
                    "active_count": len(self._alert_tailers),
                }
            )
        except Exception as e:
            self._logger.error(f"Error getting alert monitor status: {e}")
            return (
                flask.jsonify(
                    {"error": "Failed to retrieve alert monitor status"}
                ),
                500,
            )

    @octoprint.plugin.BlueprintPlugin.route("/multi-stream", methods=["GET"])
    @no_firstrun_access
    def get_active_streams(self):
        """Get list of active streaming files (multi-file support)."""
        try:
            active_files = list(self._active_tailers.keys())
            return flask.jsonify(
                {"active_streams": active_files, "count": len(active_files)}
            )

        except Exception as e:
            self._logger.error(f"Error getting active streams: {e}")
            return (
                flask.jsonify({"error": "Failed to retrieve active streams"}),
                500,
            )

    def is_blueprint_csrf_protected(self):  # type: ignore[override]
        """Explicitly require CSRF protection for blueprint routes."""
        return True

    # ~~ Helper methods

    def _log_security_event(self, event_type: str, detail: str) -> None:
        """Record a security-relevant event in the plugin log.

        This provides an audit trail for path-traversal attempts, rate-limit
        violations, and other security violations.  Details are written to the
        server log only — they are never returned to API callers.

        Args:
            event_type: Short machine-readable label
                (e.g. ``"path_traversal"``).
            detail: Human-readable description for the log entry.
        """
        self._logger.warning(f"[SECURITY] {event_type}: {detail}")

    def _get_logs_base_folder(self) -> str:
        """Resolve OctoPrint's global log directory across API variants."""
        candidates = []
        noarg_base_folder = None

        global_getter = getattr(self._settings, "global_get_basefolder", None)
        if callable(global_getter):
            try:
                # pylint: disable-next=not-callable
                candidate = global_getter("logs")
                if isinstance(candidate, str) and candidate:
                    candidates.append(candidate)
            except Exception as e:
                self._logger.debug(
                    "global_get_basefolder('logs') lookup failed: %s", e
                )

        base_folder_getter = getattr(self._settings, "getBaseFolder", None)
        if callable(base_folder_getter):
            try:
                # pylint: disable-next=not-callable
                candidate = base_folder_getter("logs")
                if isinstance(candidate, str) and candidate:
                    candidates.append(candidate)
            except TypeError:
                # OctoPrint 2.0 variants can expose
                # getBaseFolder() without args.
                # That commonly resolves to the plugin data folder, not the
                # global OctoPrint logs folder, so do not use it as a log-path
                # candidate unless every global lookup path fails.
                try:
                    # pylint: disable-next=not-callable
                    candidate = base_folder_getter()
                    if isinstance(candidate, str) and candidate:
                        noarg_base_folder = candidate
                except Exception as e:
                    self._logger.debug(
                        "getBaseFolder() fallback failed: %s", e
                    )
            except Exception as e:
                self._logger.debug(
                    "getBaseFolder('logs') lookup failed: %s", e
                )

        try:
            # pylint: disable=import-outside-toplevel
            from octoprint.settings import (
                settings as octoprint_settings,  # type: ignore[import-untyped]
            )

            global_settings = octoprint_settings()
            if global_settings is not None:
                candidate = global_settings.getBaseFolder("logs")
                if isinstance(candidate, str) and candidate:
                    candidates.append(candidate)
        except Exception as e:
            self._logger.debug(
                "octoprint.settings fallback lookup failed: %s", e
            )

        for candidate in candidates:
            if os.path.isdir(candidate):
                return candidate

        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate

        if noarg_base_folder:
            self._logger.debug(
                "Skipping no-arg getBaseFolder() result"
                " for log resolution: %s",
                noarg_base_folder,
            )

        raise RuntimeError("Unable to resolve OctoPrint global logs folder")

    def _resolve_log_path(
        self, filename, context: str
    ) -> tuple[str | None, _LogPathErrorCode | None]:
        """Validate *filename* and resolve it to a safe path in the log dir.

        This is the single chokepoint through which every user-supplied log
        filename must pass before it reaches a filesystem sink.  It enforces
        :func:`validate_filename` (no path components) followed by
        :func:`is_safe_path` (realpath containment), emitting the appropriate
        security event on rejection.

        Args:
            filename: The user/API-supplied filename.
            context: Short label for security-event logging, e.g.
                ``"search"``.

        Returns:
            ``(filepath, None)`` when the filename is valid and the resolved
            path exists as a regular file.  Otherwise ``(None, error_code)``
            where *error_code* is one of ``"invalid"``, ``"denied"`` or
            ``"not_found"``.  Callers map the code to their own response shape.
        """
        if not isinstance(filename, str) or not validate_filename(filename):
            self._log_security_event(
                "invalid_filename",
                f"Rejected filename in {context}: {filename!r}",
            )
            return None, "invalid"

        log_dir = self._get_logs_base_folder()
        if not is_safe_path(log_dir, filename):
            self._log_security_event(
                "path_traversal",
                f"Path traversal attempt in {context}: {filename!r}",
            )
            return None, "denied"

        # is_safe_path guarantees the join stays inside log_dir.
        filepath = os.path.join(log_dir, filename)
        if not os.path.isfile(filepath):
            return None, "not_found"

        return filepath, None

    def _write_unknown_debug_test_log(self, message: str) -> None:
        """Append an UNKNOWN test line directly to octoprint.log."""
        try:
            log_dir = self._get_logs_base_folder()
            filepath = os.path.join(log_dir, "octoprint.log")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
            with open(
                filepath, "a", encoding="utf-8", errors="replace"
            ) as handle:
                handle.write(
                    f"{timestamp} - {self._logger.name}"
                    f" - UNKNOWN - {message}\n"
                )
        except OSError as e:
            self._logger.error(
                f"Failed to write UNKNOWN debug test log entry: {e}"
            )

    def _start_flush_timer(self):
        """Start the periodic line-buffer flush timer."""
        interval = self._get_stream_poll_interval_seconds()
        self._flush_timer = threading.Timer(interval, self._flush_line_buffer)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _flush_line_buffer(self):
        """Flush buffered lines as a single batch WebSocket message."""
        with self._line_buffer_lock:
            if not self._line_buffer:
                # Reschedule even if empty, as long as streaming is active
                if (
                    self._tailer
                    and self._tailer.is_running()
                    or self._active_tailers
                ):
                    self._start_flush_timer()
                return
            batch = self._line_buffer[:]
            self._line_buffer.clear()

        max_lines = self._settings.get(["max_stream_lines"])
        if len(batch) > max_lines:
            batch = batch[-max_lines:]

        self._plugin_manager.send_plugin_message(
            self._identifier, {"type": "log_lines", "data": batch}
        )

        # Reschedule
        if self._tailer and self._tailer.is_running() or self._active_tailers:
            self._start_flush_timer()

    def _get_alert_monitor_files(self):
        """Resolve list of log files that should drive severity alerts."""
        log_dir = self._get_logs_base_folder()
        mode = (
            self._settings.get(["alerts_monitor_mode"]) or "selected"
        ).lower()

        if mode == "all":
            configured = self._get_available_log_filenames()
        else:
            raw = self._settings.get(["alerts_monitored_logs"])
            configured = []
            if isinstance(raw, list):
                configured = [f for f in raw if isinstance(f, str) and f]
            elif isinstance(raw, str) and raw:
                configured = [raw]

            if not configured:
                default_file = self._settings.get(["default_log_file"])
                if isinstance(default_file, str) and default_file:
                    configured = [default_file]

        unique_files = []
        seen = set()
        for filename in configured:
            if filename in seen:
                continue
            seen.add(filename)

            if not validate_filename(filename):
                continue
            if not is_safe_path(log_dir, filename):
                continue

            filepath = os.path.join(log_dir, filename)
            if os.path.isfile(filepath):
                unique_files.append(filename)

        return unique_files

    def _refresh_runtime_alert_settings(self):
        """Cache alert-related settings used in hot paths.

        Avoids per-line lookups.
        """
        severity_triggers = self._settings.get(["severity_triggers"])
        if not isinstance(severity_triggers, list):
            severity_triggers = ["WARNING", "ERROR", "CRITICAL"]

        normalized_triggers = []
        for level in severity_triggers:
            if not isinstance(level, str):
                continue
            normalized = level.strip().upper()
            if normalized and normalized not in normalized_triggers:
                normalized_triggers.append(normalized)

        if not normalized_triggers:
            normalized_triggers = ["WARNING", "ERROR", "CRITICAL"]

        max_alert_history = self._settings.get(["max_alert_history"])
        try:
            max_alert_history = int(max_alert_history)
        except (TypeError, ValueError):
            max_alert_history = 100
        max_alert_history = min(max(10, max_alert_history), MAX_HISTORY_LIMIT)

        settings_snapshot = {
            "alerts_enabled": bool(self._settings.get(["alerts_enabled"])),
            "severity_triggers": normalized_triggers,
            "alert_history_enabled": bool(
                self._settings.get(["alert_history_enabled"])
            ),
            "max_alert_history": max_alert_history,
            "enable_notifications": bool(
                self._settings.get(["enable_notifications"])
            ),
        }

        with self._runtime_settings_lock:
            self._runtime_alert_settings = settings_snapshot

    def _get_runtime_alert_settings(self):
        """Return a thread-safe snapshot of cached runtime alert settings."""
        with self._runtime_settings_lock:
            return dict(self._runtime_alert_settings)

    def _log_settings_snapshot_if_debug_enabled(self, context: str):
        """Write current plugin settings to log when debug mode is enabled."""
        if not self._settings.get(["debug_mode"]):
            return

        log_method = self._logger.debug
        if not self._logger.isEnabledFor(logging.DEBUG):
            # When OctoPrint runs without global --debug,
            # DEBUG logs are filtered.
            # Fall back to INFO so users still see the debug settings snapshot.
            log_method = self._logger.info

        def is_sensitive_key(name):
            key = str(name or "").lower()
            markers = ["password", "token", "secret", "apikey", "api_key"]
            return any(marker in key for marker in markers)

        def normalize_value(value, parent_key=""):
            if is_sensitive_key(parent_key):
                return "***"

            if isinstance(value, dict):
                result = {}
                for key, inner_value in value.items():
                    key_text = str(key)
                    result[key_text] = normalize_value(inner_value, key_text)
                return result

            if isinstance(value, list):
                return [normalize_value(item, parent_key) for item in value]

            if isinstance(value, (str, int, float, bool)) or value is None:
                return value

            return str(value)

        try:
            plugin_settings = self._settings.get([])
            if not isinstance(plugin_settings, dict):
                log_method(
                    "[Debug Settings] %s triggered, but plugin settings "
                    "snapshot is not a dict: %s",
                    context,
                    type(plugin_settings).__name__,
                )
                return

            log_method(
                "[Debug Settings] %s triggered, current plugin settings:",
                context,
            )
            for key in sorted(plugin_settings.keys()):
                normalized = normalize_value(plugin_settings[key], key)
                serialized = json.dumps(
                    normalized,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
                log_method("[Debug Settings] %s=%s", key, serialized)

        except Exception as e:
            self._logger.error(f"Failed to log debug settings snapshot: {e}")

    def _stop_alert_monitoring(self):
        """Stop all dedicated alert-monitor tailers."""
        for filename, tailer in list(self._alert_tailers.items()):
            try:
                if tailer.is_running():
                    tailer.stop()
            except Exception as e:
                self._logger.error(
                    f"Error stopping alert monitor for {filename}: {e}"
                )
        self._alert_tailers.clear()

    def _restart_alert_monitoring(self):
        """Restart dedicated alert-monitor tailers from current settings."""
        self._stop_alert_monitoring()

        if not self._settings.get(["alerts_enabled"]):
            self._logger.info(
                "Alert monitor disabled: alerts are globally disabled"
            )
            return

        files = self._get_alert_monitor_files()
        if not files:
            self._logger.info(
                "Alert monitor disabled: no valid log files configured"
            )
            return

        log_dir = self._get_logs_base_folder()
        poll_interval = self._get_stream_poll_interval_seconds()

        for filename in files:
            filepath = os.path.join(log_dir, filename)

            def make_callback(source_file):
                def callback(line):
                    line["_source_file"] = source_file
                    self._handle_alert_line(line)

                return callback

            tailer = LogTailer(
                filepath=filepath,
                callback=make_callback(filename),
                poll_interval=poll_interval,
                logger=self._logger,
            )
            if tailer.start():
                self._alert_tailers[filename] = tailer
            else:
                self._logger.warning(
                    f"Failed to start alert monitor for {filename}"
                )

        self._logger.info(
            f"Alert monitor active for {len(self._alert_tailers)} log file(s)"
        )

    def _record_alert_line(self, parsed_line, force=False):
        """Record an alert event, optionally bypassing configured triggers."""
        try:
            runtime_settings = self._get_runtime_alert_settings()

            if not force and not runtime_settings["alerts_enabled"]:
                return

            severity_triggers = runtime_settings["severity_triggers"]
            level = parsed_line.get("level", "UNKNOWN")

            if not force and level not in severity_triggers:
                return

            with self._alert_lock:
                self._alert_counts[level] = (
                    self._alert_counts.get(level, 0) + 1
                )

                if runtime_settings["alert_history_enabled"]:
                    alert_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "level": level,
                        "logger": parsed_line.get("logger", ""),
                        "message": parsed_line.get("message", ""),
                        "source_file": parsed_line.get("_source_file", ""),
                    }
                    self._alert_history.append(alert_entry)

                    max_history = runtime_settings["max_alert_history"]
                    if len(self._alert_history) > max_history:
                        self._alert_history = self._alert_history[
                            -max_history:
                        ]

            self._plugin_manager.send_plugin_message(
                self._identifier,
                {
                    "type": "severity_alert",
                    "level": level,
                    "count": self._alert_counts[level],
                    "message": parsed_line.get("message", ""),
                    "notification_enabled": runtime_settings[
                        "enable_notifications"
                    ],
                    "source_file": parsed_line.get("_source_file", ""),
                },
            )

        except Exception as e:
            self._logger.error(f"Error recording alert line: {e}")

    def _handle_alert_line(self, parsed_line):
        """Handle a log line for alert generation only.

        Independent from the UI stream.
        """
        message = parsed_line.get("message", "")
        if isinstance(message, str) and "[LogMonitor Debug Test]" in message:
            return

        self._record_alert_line(parsed_line, force=False)

    def _handle_log_line(self, parsed_line):
        """Handle a new log line from the tailer.

        Buffers it for batched WebSocket delivery only.

        Args:
            parsed_line: Parsed log line dictionary
        """
        try:
            # Optionally mask sensitive data before sending to frontend
            if self._settings.get(["mask_log_content"]):
                masked = dict(parsed_line)
                masked["message"] = mask_sensitive_data(
                    masked.get("message", "")
                )
                masked["raw"] = mask_sensitive_data(masked.get("raw", ""))
                send_line = masked
            else:
                send_line = parsed_line

            # Buffer line for batched WebSocket delivery
            with self._line_buffer_lock:
                self._line_buffer.append(send_line)

        except Exception as e:
            self._logger.error(f"Error handling log line: {e}")

    # ~~ Softwareupdate hook

    def get_update_information(self):
        """Configure Software Update Plugin integration."""
        return {
            "logmonitor": {
                "displayName": "Log Monitor",
                "displayVersion": self._plugin_version,
                "type": "github_release",
                "user": "Ajimaru",
                "repo": "OctoPrint-LogMonitor",
                "current": self._plugin_version,
                "pip": (
                    "https://github.com/Ajimaru/OctoPrint-LogMonitor"
                    "/archive/{target_version}.zip"
                ),
            }
        }


# ~~ Plugin metadata

__plugin_name__ = "Log Monitor"
__plugin_pythoncompat__ = ">=3.9,<4"
__plugin_version__ = PLUGIN_VERSION
__plugin_description__ = (
    "Live log streaming and searching for OctoPrint with severity alerting"
)
__plugin_author__ = "Ajimaru"
__plugin_url__ = "https://github.com/Ajimaru/OctoPrint-LogMonitor"
__plugin_license__ = "AGPL-3.0-or-later"


# Module-level plugin variables (populated by __plugin_load__)
__plugin_implementation__: LogmonitorPlugin | None = None
__plugin_hooks__: dict = {}


# ~~ Plugin loading
def __plugin_load__():  # noqa: N807
    """Load the plugin."""
    global __plugin_implementation__  # type: ignore
    __plugin_implementation__ = LogmonitorPlugin()

    global __plugin_hooks__  # type: ignore[reportUnnecessaryGlobalStatement]
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": (
            __plugin_implementation__.get_update_information
        )
    }
