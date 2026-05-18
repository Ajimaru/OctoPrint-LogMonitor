"""
pytest conftest – install OctoPrint stubs before any test module is imported.

octoprint_logmonitor/__init__.py imports ``octoprint.plugin`` and
``octoprint.server.util.flask`` at module level, so these stubs must exist
in ``sys.modules`` before pytest collects any test file that touches the
package.
"""

import sys
import types


def _install_fake_octoprint() -> None:
    """Register minimal OctoPrint stubs in sys.modules."""
    if "octoprint" in sys.modules:
        return

    # ---- top-level octoprint package ----------------------------------- #
    octoprint_mod = types.ModuleType("octoprint")

    # ---- octoprint.plugin ---------------------------------------------- #
    plugin_mod = types.ModuleType("octoprint.plugin")

    class _DummyBlueprintPlugin:
        @staticmethod
        def route(_rule, _methods=None, **_kwargs):  # noqa: ANN001
            """Return a no-op decorator for blueprint routes in tests."""

            def decorator(func):
                """Pass through the wrapped view function unchanged."""
                return func

            return decorator

    setattr(plugin_mod, "StartupPlugin", type("StartupPlugin", (object,), {}))
    setattr(
        plugin_mod,
        "TemplatePlugin",
        type("TemplatePlugin", (object,), {}),
    )
    setattr(
        plugin_mod,
        "SettingsPlugin",
        type(
            "SettingsPlugin",
            (object,),
            {"on_settings_save": lambda self, data: data},
        ),
    )
    setattr(plugin_mod, "AssetPlugin", type("AssetPlugin", (object,), {}))
    setattr(plugin_mod, "BlueprintPlugin", _DummyBlueprintPlugin)

    octoprint_mod.plugin = plugin_mod  # type: ignore[attr-defined]
    sys.modules["octoprint"] = octoprint_mod
    sys.modules["octoprint.plugin"] = plugin_mod

    # ---- octoprint.server.util.flask ----------------------------------- #
    server_mod = types.ModuleType("octoprint.server")
    server_util_mod = types.ModuleType("octoprint.server.util")
    server_util_flask_mod = types.ModuleType("octoprint.server.util.flask")

    def _no_firstrun_access(func):
        """No-op stand-in for OctoPrint's @no_firstrun_access decorator."""
        return func

    setattr(server_util_flask_mod, "no_firstrun_access", _no_firstrun_access)
    # Patchable placeholder used by tests via patch(…"settings")
    server_util_flask_mod.settings = None  # type: ignore[attr-defined]

    # octoprint.server needs userManager for patcher in test_plugin_core
    server_mod.userManager = None  # type: ignore[attr-defined]

    octoprint_mod.server = server_mod  # type: ignore[attr-defined]
    server_mod.util = server_util_mod  # type: ignore[attr-defined]
    server_util_mod.flask = server_util_flask_mod  # type: ignore[attr-defined]
    sys.modules["octoprint.server"] = server_mod
    sys.modules["octoprint.server.util"] = server_util_mod
    sys.modules["octoprint.server.util.flask"] = server_util_flask_mod

    # ---- octoprint.settings (used inside a function in __init__.py) --- #
    settings_mod = types.ModuleType("octoprint.settings")
    settings_mod.settings = lambda: None  # type: ignore[attr-defined]
    sys.modules["octoprint.settings"] = settings_mod


_install_fake_octoprint()
