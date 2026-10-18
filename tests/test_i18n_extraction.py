"""
Tests for translation-catalog extraction.

Guards the Babel configuration itself rather than the plugin code: a
misconfigured extractor fails silently, dropping strings from the catalog
with no error anywhere in the build.
"""

import io
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JS_FILE = (
    REPO_ROOT / "octoprint_logmonitor" / "static" / "js" / "logmonitor.js"
)
BABEL_CFG = REPO_ROOT / "babel.cfg"

KEYWORDS = {"gettext": None, "ngettext": (1, 2)}


def _babel():
    """Import Babel's extractor, skipping the test if unavailable."""
    try:
        from babel.messages.extract import extract_javascript
    except ImportError:  # pragma: no cover - babel is a dev dependency
        raise unittest.SkipTest("Babel not installed")
    return extract_javascript


class TestJavaScriptExtraction(unittest.TestCase):
    """Regression tests for the JSX-lexer bug in Babel.

    Babel's JS lexer treats the regex literal ``/>/g`` -- used by
    ``escapeHtml()`` -- as a JSX tag close when JSX support is on. From that
    token onward the file is tokenised incorrectly and every later
    ``gettext()`` call is dropped from the catalog without warning. Disabling
    JSX in babel.cfg restores correct tokenisation.
    """

    def test_babel_cfg_disables_jsx(self):
        """babel.cfg must switch JSX parsing off for the JS extractor."""
        text = BABEL_CFG.read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r"(?m)^jsx\s*=\s*$",
            "babel.cfg must contain an empty 'jsx =' line. Babel reads "
            "config values as strings and only tests truthiness, so "
            "'false' or '0' would still leave JSX enabled.",
        )

    def test_strings_after_escape_html_are_extracted(self):
        """A gettext() call late in the file must reach the catalog.

        The marker is appended past escapeHtml(), which is where the
        tokeniser used to give up.
        """
        extract_javascript = _babel()
        marker = "PROBE_MARKER_DO_NOT_TRANSLATE"
        source = JS_FILE.read_bytes() + (
            f'\nvar __probe = gettext("{marker}");\n'.encode()
        )

        rows = list(
            extract_javascript(io.BytesIO(source), KEYWORDS, [], {"jsx": ""})
        )
        found = [r for r in rows if r[2] == marker]
        self.assertTrue(
            found,
            "A gettext() call at the end of logmonitor.js was not "
            "extracted; Babel's JSX lexer has broken tokenisation again.",
        )

    def test_jsx_enabled_still_reproduces_the_bug(self):
        """Documents the failure mode the configuration protects against.

        If this ever stops failing, Babel has fixed the lexer upstream and
        the jsx workaround in babel.cfg can be reconsidered.
        """
        extract_javascript = _babel()
        marker = "PROBE_MARKER_DO_NOT_TRANSLATE"
        source = JS_FILE.read_bytes() + (
            f'\nvar __probe = gettext("{marker}");\n'.encode()
        )

        rows = list(extract_javascript(io.BytesIO(source), KEYWORDS, [], {}))
        self.assertFalse(
            [r for r in rows if r[2] == marker],
            "Babel now extracts this with JSX enabled -- the lexer bug "
            "appears fixed upstream; revisit the 'jsx =' line in babel.cfg.",
        )


if __name__ == "__main__":
    unittest.main()
