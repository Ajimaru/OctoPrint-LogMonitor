"""
OctoPrint Log Monitor Plugin

Provides live log streaming and searching capabilities with severity-based alerting.
"""

import os
import threading
from datetime import datetime

import flask
import octoprint.plugin

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


class LogmonitorPlugin(
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.BlueprintPlugin,
):
    """
    Main plugin class implementing OctoPrint Log Monitor functionality.

    Features:
    - Live log streaming via WebSocket
    - Full-text log search with severity filtering
    - Navbar and Sidebar indicators for severity alerts
    - Configurable severity triggers
    """

    def __init__(self):
        super().__init__()
        self._tailer = None
        self._searcher = None
        self._alert_counts = {}
        self._alert_lock = threading.Lock()
        self._alert_history = []  # Store alert history
        self._active_tailers = {}  # Support multi-file streaming
        # Rate-limit search API: max 10 requests per minute per client
        self._search_rate_limiter = RateLimiter(max_calls=10, period=60.0)
        # Line buffer: collect lines, flush as batch to reduce WebSocket pressure
        self._line_buffer = []
        self._line_buffer_lock = threading.Lock()
        self._flush_timer = None

    # ~~ StartupPlugin mixin

    def on_after_startup(self):
        """Initialize plugin after OctoPrint startup."""
        self._logger.info("Log Monitor Plugin started")

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

        # Auto-start streaming if enabled
        if self._settings.get(["auto_start_streaming"]):
            try:
                default_log_file = self._settings.get(["default_log_file"])
                log_dir = self._settings.getBaseFolder("logs")
                filepath = os.path.join(log_dir, default_log_file)

                if os.path.exists(filepath):
                    poll_interval = (
                        self._settings.get(["stream_poll_interval_ms"]) / 1000.0
                    )
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
                    self._logger.warning(f"Default log file not found: {filepath}")
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
                self._logger.error(f"Error stopping tailer for {filename}: {e}")

        self._active_tailers.clear()

    # ~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        """Define default plugin settings."""
        return {
            "show_navbar": True,
            "show_sidebar": True,
            "severity_triggers": ["WARNING", "ERROR", "CRITICAL"],
            "default_log_file": "octoprint.log",
            "stream_poll_interval_ms": 1000,
            "max_stream_lines": 500,
            "search_page_size": 50,
            "auto_scroll": True,
            "auto_start_streaming": False,  # NEW
            "enable_notifications": True,  # NEW
            "regex_search_enabled": False,  # NEW
            "alert_history_enabled": True,  # NEW
            "max_alert_history": 100,  # NEW
            # Mask sensitive data (API keys, passwords, emails) in streamed log lines
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

    def _get_available_log_filenames(self):
        """Return sorted list of available .log filenames from OctoPrint log folder."""
        try:
            log_dir = self._settings.getBaseFolder("logs")
            if not os.path.exists(log_dir):
                return []

            files = []
            for filename in os.listdir(log_dir):
                filepath = os.path.join(log_dir, filename)
                if os.path.isfile(filepath) and filename.endswith(".log"):
                    files.append(filename)

            return sorted(files)
        except Exception as e:
            self._logger.error(f"Error listing log filenames for template vars: {e}")
            return []

    # ~~ BlueprintPlugin mixin

    @octoprint.plugin.BlueprintPlugin.route("/files", methods=["GET"])
    def get_log_files(self):
        """Get list of available log files."""
        try:
            log_dir = self._settings.getBaseFolder("logs")

            if not os.path.exists(log_dir):
                return flask.jsonify({"files": [], "error": "Log directory not found"})

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
            return flask.jsonify({"files": [], "error": str(e)}), 500

    @octoprint.plugin.BlueprintPlugin.route("/search", methods=["GET"])
    def search_logs(self):
        """Search logs with pagination and severity filtering."""
        try:
            # --- Rate limiting ---
            client_ip = flask.request.remote_addr or "unknown"
            if not self._search_rate_limiter.is_allowed(client_ip):
                self._log_security_event(
                    "rate_limit_exceeded", f"Search rate limit exceeded for {client_ip}"
                )
                return (
                    flask.jsonify({"error": "Too many requests. Please slow down."}),
                    429,
                )

            # --- Parse & validate parameters ---
            filename = flask.request.args.get(
                "file", self._settings.get(["default_log_file"])
            )
            query = flask.request.args.get("query", "")
            raw_levels = flask.request.args.getlist("levels")
            case_sensitive = (
                flask.request.args.get("case_sensitive", "false").lower() == "true"
            )
            use_regex = flask.request.args.get("use_regex", "false").lower() == "true"

            # Validate and clamp offset / limit
            try:
                offset = int(flask.request.args.get("offset", 0))
                limit = int(
                    flask.request.args.get(
                        "limit", self._settings.get(["search_page_size"])
                    )
                )
            except (ValueError, TypeError):
                return (
                    flask.jsonify({"error": "offset and limit must be integers"}),
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
                            "error": f"Invalid severity level(s): {', '.join(invalid_levels)}"
                        }
                    ),
                    400,
                )

            # --- Filename / path validation ---
            if not validate_filename(filename):
                self._log_security_event(
                    "invalid_filename", f"Rejected filename in search: {filename!r}"
                )
                return flask.jsonify({"error": "Invalid filename"}), 400

            log_dir = self._settings.getBaseFolder("logs")
            if not is_safe_path(log_dir, filename):
                self._log_security_event(
                    "path_traversal", f"Path traversal attempt in search: {filename!r}"
                )
                return flask.jsonify({"error": "Access denied"}), 403

            filepath = os.path.join(log_dir, filename)

            if not os.path.isfile(filepath):
                return flask.jsonify({"error": "Log file not found"}), 404

            # --- File-size guard ---
            if not check_file_size(filepath):
                self._logger.warning(f"Search rejected: file too large: {filename}")
                return flask.jsonify({"error": "Log file is too large to process"}), 413

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
                flask.jsonify({"error": "Search failed. See server log for details."}),
                500,
            )

    @octoprint.plugin.BlueprintPlugin.route("/stream/start", methods=["POST"])
    def start_stream(self):
        """Start or switch log streaming."""
        try:
            data = flask.request.get_json(silent=True) or {}
            filename = data.get("file", self._settings.get(["default_log_file"]))

            # --- Filename / path validation ---
            if not validate_filename(filename):
                self._log_security_event(
                    "invalid_filename",
                    f"Rejected filename in stream/start: {filename!r}",
                )
                return flask.jsonify({"error": "Invalid filename"}), 400

            log_dir = self._settings.getBaseFolder("logs")
            if not is_safe_path(log_dir, filename):
                self._log_security_event(
                    "path_traversal",
                    f"Path traversal attempt in stream/start: {filename!r}",
                )
                return flask.jsonify({"error": "Access denied"}), 403

            filepath = os.path.join(log_dir, filename)

            if not os.path.isfile(filepath):
                return flask.jsonify({"error": "Log file not found"}), 404

            # --- File-size guard ---
            if not check_file_size(filepath):
                self._logger.warning(f"Stream rejected: file too large: {filename}")
                return flask.jsonify({"error": "Log file is too large to stream"}), 413

            # Stop existing tailer if running
            if self._tailer and self._tailer.is_running():
                self._tailer.stop()

            # Create new tailer
            poll_interval = self._settings.get(["stream_poll_interval_ms"]) / 1000.0
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
                initial_lines = self._tailer.get_last_n_lines(initial_lines_count)

                return flask.jsonify(
                    {
                        "status": "started",
                        "file": filename,
                        "initial_lines": initial_lines,
                    }
                )
            else:
                return flask.jsonify({"error": "Failed to start streaming"}), 500

        except Exception as e:
            self._logger.error(f"Error starting stream: {e}")
            return flask.jsonify({"error": str(e)}), 500

    @octoprint.plugin.BlueprintPlugin.route("/stream/stop", methods=["POST"])
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

    @octoprint.plugin.BlueprintPlugin.route("/stream/multi/start", methods=["POST"])
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
                    flask.jsonify({"error": "Too many files specified (max 20)"}),
                    400,
                )

            log_dir = self._settings.getBaseFolder("logs")
            started_files = []
            failed_files = []

            for filename in files:
                if not isinstance(filename, str):
                    failed_files.append(
                        {"file": str(filename), "error": "Invalid filename"}
                    )
                    continue

                # Validate filename and path
                if not validate_filename(filename):
                    self._log_security_event(
                        "invalid_filename",
                        f"Rejected filename in multi-stream: {filename!r}",
                    )
                    failed_files.append({"file": filename, "error": "Invalid filename"})
                    continue

                if not is_safe_path(log_dir, filename):
                    self._log_security_event(
                        "path_traversal",
                        f"Path traversal attempt in multi-stream: {filename!r}",
                    )
                    failed_files.append({"file": filename, "error": "Access denied"})
                    continue

                filepath = os.path.join(log_dir, filename)

                if not os.path.isfile(filepath):
                    failed_files.append({"file": filename, "error": "File not found"})
                    continue

                # File-size guard
                if not check_file_size(filepath):
                    self._logger.warning(
                        f"Multi-stream rejected: file too large: {filename}"
                    )
                    failed_files.append(
                        {"file": filename, "error": "File is too large to stream"}
                    )
                    continue

                # Stop existing tailer for this file if any
                if filename in self._active_tailers:
                    try:
                        self._active_tailers[filename].stop()
                    except Exception:
                        pass

                # Create new tailer
                poll_interval = self._settings.get(["stream_poll_interval_ms"]) / 1000.0

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
                    failed_files.append({"file": filename, "error": "Failed to start"})

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
            return flask.jsonify({"error": "Failed to start multi-stream"}), 500

    @octoprint.plugin.BlueprintPlugin.route("/stream/multi/stop", methods=["POST"])
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
                    if not isinstance(filename, str) or not validate_filename(filename):
                        continue
                    if filename in self._active_tailers:
                        try:
                            self._active_tailers[filename].stop()
                            del self._active_tailers[filename]
                            stopped_files.append(filename)
                        except Exception as e:
                            self._logger.error(f"Error stopping {filename}: {e}")

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

    @octoprint.plugin.BlueprintPlugin.route("/export", methods=["POST"])
    def export_results(self):
        """Export search results to CSV or TXT format."""
        try:
            data = flask.request.get_json(silent=True) or {}
            results = data.get("results", [])
            format_type = data.get("format", "csv").lower()

            # Guard against excessively large export payloads
            if not isinstance(results, list) or len(results) > MAX_SEARCH_LIMIT:
                return (
                    flask.jsonify(
                        {
                            "error": f"results must be a list of at most {MAX_SEARCH_LIMIT} entries"
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
                headers={"Content-Disposition": f"attachment;filename={filename}"},
            )

        except Exception as e:
            self._logger.error(f"Error exporting results: {e}")
            return flask.jsonify({"error": "Export failed"}), 500

    @octoprint.plugin.BlueprintPlugin.route(
        "/download/<path:filename>", methods=["GET"]
    )
    def download_log_file(self, filename):
        """Download a log file directly."""
        try:
            # --- Filename / path validation ---
            if not validate_filename(filename):
                self._log_security_event(
                    "invalid_filename", f"Rejected filename in download: {filename!r}"
                )
                return flask.jsonify({"error": "Invalid filename"}), 400

            log_dir = self._settings.getBaseFolder("logs")
            if not is_safe_path(log_dir, filename):
                self._log_security_event(
                    "path_traversal",
                    f"Path traversal attempt in download: {filename!r}",
                )
                return flask.jsonify({"error": "Access denied"}), 403

            filepath = os.path.join(log_dir, filename)

            if not os.path.isfile(filepath):
                return flask.jsonify({"error": "File not found"}), 404

            return flask.send_file(filepath, as_attachment=True, download_name=filename)

        except Exception as e:
            self._logger.error(f"Error downloading file: {e}")
            return flask.jsonify({"error": "Download failed"}), 500

    @octoprint.plugin.BlueprintPlugin.route("/alert-history", methods=["GET"])
    def get_alert_history(self):
        """Get alert history."""
        try:
            try:
                limit = int(flask.request.args.get("limit", 100))
            except (ValueError, TypeError):
                return flask.jsonify({"error": "limit must be an integer"}), 400

            # Clamp to safe maximum
            limit = min(max(1, limit), MAX_HISTORY_LIMIT)

            with self._alert_lock:
                history = self._alert_history[-limit:]
                total = len(self._alert_history)

            return flask.jsonify({"history": history, "total": total})

        except Exception as e:
            self._logger.error(f"Error getting alert history: {e}")
            return flask.jsonify({"error": "Failed to retrieve alert history"}), 500

    @octoprint.plugin.BlueprintPlugin.route("/alert-history/clear", methods=["POST"])
    def clear_alert_history(self):
        """Clear alert history."""
        try:
            with self._alert_lock:
                self._alert_history = []

            return flask.jsonify({"status": "cleared"})

        except Exception as e:
            self._logger.error(f"Error clearing alert history: {e}")
            return flask.jsonify({"error": "Failed to clear alert history"}), 500

    @octoprint.plugin.BlueprintPlugin.route("/multi-stream", methods=["GET"])
    def get_active_streams(self):
        """Get list of active streaming files (multi-file support)."""
        try:
            active_files = list(self._active_tailers.keys())
            return flask.jsonify(
                {"active_streams": active_files, "count": len(active_files)}
            )

        except Exception as e:
            self._logger.error(f"Error getting active streams: {e}")
            return flask.jsonify({"error": "Failed to retrieve active streams"}), 500

    # ~~ Helper methods

    def _log_security_event(self, event_type: str, detail: str) -> None:
        """
        Record a security-relevant event in the plugin log.

        This provides an audit trail for path-traversal attempts, rate-limit
        violations, and other security violations.  Details are written to the
        server log only — they are never returned to API callers.

        Args:
            event_type: Short machine-readable label (e.g. ``"path_traversal"``)
            detail: Human-readable description for the log entry.
        """
        self._logger.warning(f"[SECURITY] {event_type}: {detail}")

    def _start_flush_timer(self):
        """Start the periodic line-buffer flush timer."""
        interval = max(0.5, self._settings.get(["stream_poll_interval_ms"]) / 1000.0)
        self._flush_timer = threading.Timer(interval, self._flush_line_buffer)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _flush_line_buffer(self):
        """Flush buffered lines as a single batch WebSocket message."""
        with self._line_buffer_lock:
            if not self._line_buffer:
                # Reschedule even if empty, as long as streaming is active
                if self._tailer and self._tailer.is_running() or self._active_tailers:
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

    def _handle_log_line(self, parsed_line):
        """
        Handle a new log line from the tailer.
        Buffers it for batched WebSocket delivery; checks severity alerts immediately.

        Args:
            parsed_line: Parsed log line dictionary
        """
        try:
            # Check if this severity should trigger an alert
            severity_triggers = self._settings.get(["severity_triggers"])
            level = parsed_line.get("level", "UNKNOWN")

            if level in severity_triggers:
                with self._alert_lock:
                    self._alert_counts[level] = self._alert_counts.get(level, 0) + 1

                    # Add to alert history (NEW)
                    if self._settings.get(["alert_history_enabled"]):
                        alert_entry = {
                            "timestamp": datetime.now().isoformat(),
                            "level": level,
                            "logger": parsed_line.get("logger", ""),
                            "message": parsed_line.get("message", ""),
                        }
                        self._alert_history.append(alert_entry)

                        # Trim history if exceeds max
                        max_history = self._settings.get(["max_alert_history"])
                        if len(self._alert_history) > max_history:
                            self._alert_history = self._alert_history[-max_history:]

                # Send alert message
                self._plugin_manager.send_plugin_message(
                    self._identifier,
                    {
                        "type": "severity_alert",
                        "level": level,
                        "count": self._alert_counts[level],
                        "message": parsed_line.get("message", ""),
                        "notification_enabled": self._settings.get(
                            ["enable_notifications"]
                        ),
                    },
                )

            # Optionally mask sensitive data before sending to frontend
            if self._settings.get(["mask_log_content"]):
                masked = dict(parsed_line)
                masked["message"] = mask_sensitive_data(masked.get("message", ""))
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
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_version__ = "0.1.0"
__plugin_description__ = (
    "Live log streaming and searching for OctoPrint with severity alerting"
)
__plugin_author__ = "Ajimaru"
__plugin_url__ = "https://github.com/Ajimaru/OctoPrint-LogMonitor"
__plugin_license__ = "AGPL-3.0-or-later"


# ~~ Plugin loading
def __plugin_load__():
    """Load the plugin."""
    global __plugin_implementation__
    __plugin_implementation__ = LogmonitorPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": (
            __plugin_implementation__.get_update_information
        )
    }
