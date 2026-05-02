"""
Unit tests for core plugin behaviors in octoprint_logmonitor.__init__.

These tests run without a real OctoPrint environment by stubbing the
required OctoPrint plugin mixins.
"""

# pylint: disable=protected-access,missing-function-docstring,too-many-public-methods

import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import flask

from octoprint_logmonitor.security import MAX_HISTORY_LIMIT, MAX_SEARCH_LIMIT


def _install_fake_octoprint():
    """Stub octoprint.plugin so the plugin module imports without OctoPrint."""
    if "octoprint" in sys.modules:
        return

    octoprint_module = types.ModuleType("octoprint")
    fake_plugin = types.ModuleType("octoprint.plugin")

    # pylint: disable=too-few-public-methods
    class DummyBlueprintPlugin:
        """Minimal BlueprintPlugin stand-in providing a no-op route decorator."""

        @staticmethod
        def route(_rule, methods=None, **_kwargs):  # pylint: disable=unused-argument
            """No-op route decorator that returns the view function unchanged."""

            def decorator(func):
                return func

            return decorator

    fake_plugin.StartupPlugin = type("StartupPlugin", (object,), {})  # type: ignore[attr-defined]
    fake_plugin.TemplatePlugin = type("TemplatePlugin", (object,), {})  # type: ignore[attr-defined]
    fake_plugin.SettingsPlugin = type(  # type: ignore[attr-defined]
        "SettingsPlugin",
        (object,),
        {"on_settings_save": lambda self, data: data},
    )
    fake_plugin.AssetPlugin = type("AssetPlugin", (object,), {})  # type: ignore[attr-defined]
    fake_plugin.BlueprintPlugin = DummyBlueprintPlugin  # type: ignore[attr-defined]

    octoprint_module.plugin = fake_plugin  # type: ignore[attr-defined]
    sys.modules["octoprint"] = octoprint_module
    sys.modules["octoprint.plugin"] = fake_plugin


_install_fake_octoprint()

import octoprint_logmonitor as plugin_module  # noqa: E402  pylint: disable=wrong-import-position


class FakeSettings:
    """Minimal settings stub for plugin tests."""

    def __init__(self, base_dir, values):
        self._base_dir = base_dir
        self._values = values

    def get(self, keys):
        """Return setting value by key (or first key from a list)."""
        if isinstance(keys, list):
            return self._values.get(keys[0])
        return self._values.get(keys)

    def getBaseFolder(self, _name):  # pylint: disable=invalid-name
        """Return the configured base folder (OctoPrint-style camelCase API)."""
        return self._base_dir


class TestPluginCore(unittest.TestCase):
    """Unit tests for core plugin behaviors."""

    @staticmethod
    def _resp(result):
        """Return Flask Response, unwrapping (response, status) tuples."""
        return result[0] if isinstance(result, tuple) else result

    @staticmethod
    def _status(result) -> int:
        """Return the HTTP status code regardless of tuple/Response form."""
        return result[1] if isinstance(result, tuple) else result.status_code

    def setUp(self):
        self.app = flask.Flask(__name__)
        self.temp_dir = tempfile.mkdtemp()
        # Annotated as Any so MagicMock assignments to typed attributes
        # (_logger, _plugin_manager, _settings, etc.) don't trip the type checker.
        self.plugin: Any = plugin_module.LogmonitorPlugin()
        self.plugin._logger = MagicMock()
        self.plugin._plugin_manager = MagicMock()
        self.plugin._identifier = "logmonitor"
        self.plugin._plugin_version = "0.1.0"
        defaults = self.plugin.get_settings_defaults()
        self.plugin._settings = FakeSettings(self.temp_dir, defaults)
        self.plugin._alert_counts = {
            "DEBUG": 0,
            "INFO": 0,
            "WARNING": 0,
            "ERROR": 0,
            "CRITICAL": 0,
        }
        self.plugin._alert_history = []
        self.plugin._active_tailers = {}

    def tearDown(self):
        for child in Path(self.temp_dir).glob("*"):
            child.unlink(missing_ok=True)
        Path(self.temp_dir).rmdir()

    def test_get_settings_defaults_contains_expected_keys(self):
        defaults = self.plugin.get_settings_defaults()
        self.assertTrue(defaults["show_navbar"])
        self.assertTrue(defaults["show_sidebar"])
        self.assertEqual(defaults["default_log_file"], "octoprint.log")
        self.assertFalse(defaults["auto_start_streaming"])
        self.assertFalse(defaults["mask_log_content"])

    def test_get_assets_and_templates(self):
        assets = self.plugin.get_assets()
        self.assertIn("js", assets)
        self.assertIn("css", assets)
        configs = self.plugin.get_template_configs()
        config_types = {cfg["type"] for cfg in configs}
        self.assertTrue({"tab", "navbar", "sidebar", "settings"}.issubset(config_types))

    def test_get_template_configs_hide_widgets_when_disabled(self):
        values = dict(self.plugin.get_settings_defaults())
        values.update(
            {
                "show_navbar": False,
                "show_sidebar": False,
            }
        )
        self.plugin._settings = FakeSettings(self.temp_dir, values)

        configs = {cfg["type"]: cfg for cfg in self.plugin.get_template_configs()}

        self.assertEqual(configs["navbar"]["styles"], ["display: none"])
        self.assertEqual(configs["sidebar"]["styles_wrapper"], ["display: none"])

    def test_get_log_files_filters_and_sorts(self):
        (Path(self.temp_dir) / "b.log").write_text("b")
        (Path(self.temp_dir) / "a.log").write_text("a")
        (Path(self.temp_dir) / "notes.txt").write_text("n")

        with self.app.test_request_context("/files", method="GET"):
            response = self.plugin.get_log_files()

        payload = self._resp(response).get_json()
        filenames = [entry["name"] for entry in payload["files"]]
        self.assertEqual(filenames, ["a.log", "b.log"])

    def test_handle_log_line_triggers_alert_and_masks(self):
        values = dict(self.plugin.get_settings_defaults())
        values.update(
            {
                "severity_triggers": ["ERROR"],
                "alert_history_enabled": True,
                "max_alert_history": 1,
                "enable_notifications": True,
                "mask_log_content": True,
            }
        )
        self.plugin._settings = FakeSettings(self.temp_dir, values)

        parsed_line = {
            "timestamp": "2026-02-19 10:00:02,000",
            "logger": "plugin.test",
            "level": "ERROR",
            "message": "api_key=secret123",
            "raw": "api_key=secret123",
        }
        self.plugin._handle_log_line(parsed_line)

        self.assertEqual(self.plugin._alert_counts["ERROR"], 1)
        self.assertEqual(len(self.plugin._alert_history), 1)

        # Alert message is still sent immediately via WebSocket
        calls = self.plugin._plugin_manager.send_plugin_message.call_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[1]["type"], "severity_alert")

        # Log line goes into buffer (masked)
        self.assertEqual(len(self.plugin._line_buffer), 1)
        log_line_payload = self.plugin._line_buffer[0]
        self.assertNotIn("secret123", log_line_payload["message"])
        self.assertNotIn("secret123", log_line_payload["raw"])

    def test_search_logs_rate_limited(self):
        self.plugin._search_rate_limiter = MagicMock()
        self.plugin._search_rate_limiter.is_allowed.return_value = False

        with self.app.test_request_context("/search", method="GET"):
            response = self.plugin.search_logs()

        self.assertEqual(self._status(response), 429)

    def test_search_logs_invalid_offset_limit(self):
        with self.app.test_request_context("/search?offset=bad&limit=5", method="GET"):
            response = self.plugin.search_logs()

        self.assertEqual(self._status(response), 400)

    def test_search_logs_invalid_severity(self):
        with self.app.test_request_context("/search?levels=NOPE", method="GET"):
            response = self.plugin.search_logs()

        self.assertEqual(self._status(response), 400)

    def test_search_logs_rejects_invalid_filename(self):
        with self.app.test_request_context("/search?file=../bad.log", method="GET"):
            response = self.plugin.search_logs()

        self.assertEqual(self._status(response), 400)

    def test_search_logs_missing_file(self):
        with self.app.test_request_context("/search?file=missing.log", method="GET"):
            response = self.plugin.search_logs()

        self.assertEqual(self._status(response), 404)

    def test_search_logs_rejects_large_file(self):
        log_path = Path(self.temp_dir) / "octoprint.log"
        log_path.write_text("line")

        with patch(
            "octoprint_logmonitor.__init__.check_file_size", return_value=False
        ), self.app.test_request_context("/search?file=octoprint.log", method="GET"):
            response = self.plugin.search_logs()

        self.assertEqual(self._status(response), 413)

    def test_search_logs_success(self):
        log_path = Path(self.temp_dir) / "octoprint.log"
        log_path.write_text("line")
        self.plugin._searcher = MagicMock()
        self.plugin._searcher.search.return_value = {
            "results": [],
            "total": 0,
            "offset": 0,
            "limit": 50,
        }

        with self.app.test_request_context("/search?file=octoprint.log", method="GET"):
            response = self.plugin.search_logs()

        payload = self._resp(response).get_json()
        self.assertEqual(payload["total"], 0)

    def test_reset_alerts_endpoint(self):
        self.plugin._alert_counts["ERROR"] = 3
        with self.app.test_request_context("/alerts/reset", method="POST"):
            response = self.plugin.reset_alerts()
        self.assertEqual(self._resp(response).get_json()["status"], "reset")
        self.assertEqual(self.plugin._alert_counts["ERROR"], 0)

    def test_alert_history_endpoints(self):
        self.plugin._alert_history = [
            {"timestamp": "t1", "level": "ERROR", "logger": "a", "message": "m1"},
            {"timestamp": "t2", "level": "ERROR", "logger": "b", "message": "m2"},
        ]
        with self.app.test_request_context("/alert-history?limit=1", method="GET"):
            response = self.plugin.get_alert_history()
        payload = self._resp(response).get_json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual(len(payload["history"]), 1)

        with self.app.test_request_context("/alert-history/clear", method="POST"):
            response = self.plugin.clear_alert_history()
        self.assertEqual(self._resp(response).get_json()["status"], "cleared")
        self.assertEqual(self.plugin._alert_history, [])

    def test_alert_history_invalid_limit(self):
        with self.app.test_request_context("/alert-history?limit=bad", method="GET"):
            result = self.plugin.get_alert_history()
        status_code = result[1] if isinstance(result, tuple) else result.status_code
        self.assertEqual(status_code, 400)

    def test_start_stream_rejects_invalid_filename(self):
        with self.app.test_request_context(
            "/stream/start", method="POST", json={"file": "../bad.log"}
        ):
            response = self.plugin.start_stream()
        self.assertEqual(self._status(response), 400)

    def test_start_stream_missing_file(self):
        with self.app.test_request_context(
            "/stream/start", method="POST", json={"file": "missing.log"}
        ):
            response = self.plugin.start_stream()
        self.assertEqual(self._status(response), 404)

    def test_start_stream_success(self):
        log_path = Path(self.temp_dir) / "octoprint.log"
        log_path.write_text("line 1\nline 2\n")

        tailer = MagicMock()
        tailer.start.return_value = True
        tailer.get_last_n_lines.return_value = [{"raw": "line 2"}]

        with patch(
            "octoprint_logmonitor.__init__.LogTailer", return_value=tailer
        ), self.app.test_request_context(
            "/stream/start", method="POST", json={"file": "octoprint.log"}
        ):
            response = self.plugin.start_stream()

        payload = self._resp(response).get_json()
        self.assertEqual(payload["status"], "started")
        self.assertEqual(payload["file"], "octoprint.log")
        self.assertEqual(payload["initial_lines"], [{"raw": "line 2"}])

    def test_stop_stream_behavior(self):
        tailer = MagicMock()
        tailer.is_running.return_value = True
        self.plugin._tailer = tailer

        with self.app.test_request_context("/stream/stop", method="POST"):
            response = self.plugin.stop_stream()
        self.assertEqual(self._resp(response).get_json()["status"], "stopped")
        self.assertIsNone(self.plugin._tailer)

        with self.app.test_request_context("/stream/stop", method="POST"):
            response = self.plugin.stop_stream()
        self.assertEqual(self._resp(response).get_json()["status"], "not_running")

    def test_export_results_csv(self):
        self.plugin._searcher = MagicMock()
        self.plugin._searcher.export_to_csv.return_value = "a,b\n"

        with self.app.test_request_context(
            "/export", method="POST", json={"format": "csv", "results": []}
        ):
            response = self.plugin.export_results()
        self.assertEqual(self._resp(response).mimetype, "text/csv")

    def test_export_results_rejects_invalid_format(self):
        with self.app.test_request_context(
            "/export", method="POST", json={"format": "xml", "results": []}
        ):
            response = self.plugin.export_results()

        self.assertEqual(self._status(response), 400)

    def test_export_results_rejects_large_payload(self):
        with self.app.test_request_context(
            "/export",
            method="POST",
            json={"format": "csv", "results": ["x"] * (MAX_SEARCH_LIMIT + 1)},
        ):
            response = self.plugin.export_results()

        self.assertEqual(self._status(response), 400)

    def test_download_log_file(self):
        log_path = Path(self.temp_dir) / "octoprint.log"
        log_path.write_text("line 1")

        with self.app.test_request_context("/download/octoprint.log", method="GET"):
            response = self.plugin.download_log_file("octoprint.log")
        self.assertEqual(self._status(response), 200)
        disposition = self._resp(response).headers.get("Content-Disposition", "")
        self.assertIn("attachment;", disposition)

    def test_download_log_file_rejects_invalid_filename(self):
        with self.app.test_request_context("/download/../bad.log", method="GET"):
            response = self.plugin.download_log_file("../bad.log")
        self.assertEqual(self._status(response), 400)

    def test_download_log_file_missing(self):
        with self.app.test_request_context("/download/missing.log", method="GET"):
            response = self.plugin.download_log_file("missing.log")
        self.assertEqual(self._status(response), 404)

    def test_get_active_streams(self):
        self.plugin._active_tailers = {"a.log": MagicMock(), "b.log": MagicMock()}
        with self.app.test_request_context("/multi-stream", method="GET"):
            response = self.plugin.get_active_streams()
        payload = self._resp(response).get_json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(set(payload["active_streams"]), {"a.log", "b.log"})

    def test_get_update_information(self):
        info = self.plugin.get_update_information()
        self.assertIn("logmonitor", info)
        self.assertEqual(info["logmonitor"]["repo"], "OctoPrint-LogMonitor")

    def test_start_multi_stream_validates_payload(self):
        with self.app.test_request_context(
            "/stream/multi/start", method="POST", json={"files": "not-a-list"}
        ):
            response = self.plugin.start_multi_stream()
        self.assertEqual(self._status(response), 400)

    def test_start_multi_stream_limits_count(self):
        with self.app.test_request_context(
            "/stream/multi/start", method="POST", json={"files": ["a.log"] * 25}
        ):
            response = self.plugin.start_multi_stream()
        self.assertEqual(self._status(response), 400)

    def test_start_multi_stream_success(self):
        (Path(self.temp_dir) / "a.log").write_text("a")
        (Path(self.temp_dir) / "b.log").write_text("b")

        tailer = MagicMock()
        tailer.start.return_value = True

        with patch(
            "octoprint_logmonitor.__init__.LogTailer", return_value=tailer
        ), self.app.test_request_context(
            "/stream/multi/start", method="POST", json={"files": ["a.log", "b.log"]}
        ):
            response = self.plugin.start_multi_stream()

        payload = self._resp(response).get_json()
        self.assertEqual(payload["status"], "multi_started")
        self.assertEqual(set(payload["started"]), {"a.log", "b.log"})

    def test_stop_multi_stream_stop_all(self):
        self.plugin._active_tailers = {
            "a.log": MagicMock(),
            "b.log": MagicMock(),
        }
        with self.app.test_request_context(
            "/stream/multi/stop",
            method="POST",
            json={"files": ["a.log"], "stop_all": True},
        ):
            response = self.plugin.stop_multi_stream()

        payload = self._resp(response).get_json()
        self.assertEqual(payload["status"], "all_stopped")
        self.assertEqual(len(self.plugin._active_tailers), 0)

    def test_on_shutdown_stops_tailers(self):
        tailer = MagicMock()
        tailer.is_running.return_value = True
        self.plugin._tailer = tailer
        self.plugin._active_tailers = {
            "a.log": MagicMock(),
            "b.log": MagicMock(),
        }

        self.plugin.on_shutdown()

        tailer.stop.assert_called_once()
        self.assertEqual(self.plugin._active_tailers, {})

    def test_on_after_startup_auto_start_success(self):
        log_path = Path(self.temp_dir) / "octoprint.log"
        log_path.write_text("line")
        values = dict(self.plugin.get_settings_defaults())
        values.update(
            {
                "auto_start_streaming": True,
                "default_log_file": "octoprint.log",
                "stream_poll_interval_ms": 100,
            }
        )
        self.plugin._settings = FakeSettings(self.temp_dir, values)

        tailer = MagicMock()
        tailer.start.return_value = True

        with patch("octoprint_logmonitor.__init__.LogTailer", return_value=tailer):
            self.plugin.on_after_startup()

        tailer.start.assert_called_once()
        self.assertIsNotNone(self.plugin._tailer)

    def test_on_after_startup_missing_default_file(self):
        values = dict(self.plugin.get_settings_defaults())
        values.update(
            {
                "auto_start_streaming": True,
                "default_log_file": "missing.log",
            }
        )
        self.plugin._settings = FakeSettings(self.temp_dir, values)

        self.plugin.on_after_startup()
        self.plugin._logger.warning.assert_called()

    def test_get_log_files_missing_directory(self):
        missing_dir = Path(self.temp_dir) / "nope"
        self.plugin._settings = FakeSettings(
            str(missing_dir), self.plugin.get_settings_defaults()
        )

        with self.app.test_request_context("/files", method="GET"):
            response = self.plugin.get_log_files()

        payload = self._resp(response).get_json()
        self.assertEqual(payload["files"], [])
        self.assertIn("error", payload)

    def test_handle_log_line_without_alert(self):
        values = dict(self.plugin.get_settings_defaults())
        values.update(
            {
                "severity_triggers": ["ERROR"],
                "alert_history_enabled": True,
                "mask_log_content": False,
            }
        )
        self.plugin._settings = FakeSettings(self.temp_dir, values)

        parsed_line = {
            "timestamp": "2026-02-19 10:00:02,000",
            "logger": "plugin.test",
            "level": "INFO",
            "message": "info message",
            "raw": "info message",
        }
        self.plugin._handle_log_line(parsed_line)

        self.assertEqual(self.plugin._alert_counts["ERROR"], 0)
        # No WebSocket message sent (line is buffered, not pushed directly)
        calls = self.plugin._plugin_manager.send_plugin_message.call_args_list
        self.assertEqual(len(calls), 0)
        # Line ends up in the buffer
        self.assertEqual(len(self.plugin._line_buffer), 1)
        self.assertEqual(self.plugin._line_buffer[0]["level"], "INFO")

    def test_get_alert_history_clamps_limit(self):
        self.plugin._alert_history = [
            {"timestamp": f"t{i}", "level": "ERROR", "logger": "x", "message": "m"}
            for i in range(MAX_HISTORY_LIMIT + 10)
        ]
        with self.app.test_request_context("/alert-history?limit=9999", method="GET"):
            response = self.plugin.get_alert_history()
        payload = self._resp(response).get_json()
        self.assertEqual(len(payload["history"]), MAX_HISTORY_LIMIT)

    def test_export_results_txt(self):
        self.plugin._searcher = MagicMock()
        self.plugin._searcher.export_to_txt.return_value = "line\n"

        with self.app.test_request_context(
            "/export", method="POST", json={"format": "txt", "results": []}
        ):
            response = self.plugin.export_results()
        self.assertEqual(self._resp(response).mimetype, "text/plain")

    def test_start_stream_rejects_large_file(self):
        log_path = Path(self.temp_dir) / "octoprint.log"
        log_path.write_text("line")

        with patch(
            "octoprint_logmonitor.__init__.check_file_size", return_value=False
        ), self.app.test_request_context(
            "/stream/start", method="POST", json={"file": "octoprint.log"}
        ):
            response = self.plugin.start_stream()

        self.assertEqual(self._status(response), 413)

    def test_start_multi_stream_invalid_entries(self):
        (Path(self.temp_dir) / "a.log").write_text("a")

        with self.app.test_request_context(
            "/stream/multi/start",
            method="POST",
            json={"files": [123, "../bad.log", "missing.log", "a.log"]},
        ):
            response = self.plugin.start_multi_stream()

        payload = self._resp(response).get_json()
        self.assertEqual(payload["status"], "multi_started")
        self.assertIn("a.log", payload["started"])
        self.assertGreaterEqual(len(payload["failed"]), 2)

    def test_stop_multi_stream_subset(self):
        self.plugin._active_tailers = {
            "a.log": MagicMock(),
            "b.log": MagicMock(),
        }
        with self.app.test_request_context(
            "/stream/multi/stop", method="POST", json={"files": ["a.log"]}
        ):
            response = self.plugin.stop_multi_stream()

        payload = self._resp(response).get_json()
        self.assertEqual(payload["status"], "multi_stopped")
        self.assertIn("a.log", payload["stopped"])
        self.assertEqual(set(self.plugin._active_tailers.keys()), {"b.log"})


if __name__ == "__main__":
    unittest.main()
