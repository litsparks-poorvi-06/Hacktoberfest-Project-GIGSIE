"""Import checks for app.py.

The Streamlit script is wrapped in ``main()`` guarded by
``if __name__ == "__main__"``. Streamlit runs scripts as the ``__main__`` module,
so the UI starts under ``streamlit run app.py`` - but a plain ``import app`` only
defines functions and never renders anything. These tests confirm that contract,
so the module stays safe to import in tests.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402


class AppImportTests(unittest.TestCase):
    def test_module_imports(self) -> None:
        self.assertTrue(hasattr(app, "main"))

    def test_main_is_callable(self) -> None:
        self.assertTrue(callable(app.main))

    def test_expected_renderers_are_defined(self) -> None:
        for name in (
            "render_landing",
            "render_business",
            "render_student",
        ):
            self.assertTrue(callable(getattr(app, name)))

    def test_business_flow_helpers_are_defined(self) -> None:
        for name in ("_render_request_form", "_render_brief_editor", "_handle_publish"):
            self.assertTrue(callable(getattr(app, name)))


if __name__ == "__main__":
    unittest.main()
