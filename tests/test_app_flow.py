"""End-to-end checks for the Streamlit business flow (app.py).

These use Streamlit's official ``AppTest`` harness to actually run app.py, but
the AI call is mocked and storage is redirected to a temporary folder - so no
API credits are spent and your real ``data/`` files are never touched.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gigsie_ai  # noqa: E402
import storage  # noqa: E402

try:
    from streamlit.testing.v1 import AppTest  # noqa: E402
except Exception:  # pragma: no cover - older Streamlit without the test API
    AppTest = None

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

# A realistic brief the mocked AI "returns".
FAKE_RESULT = {
    "brief": {
        "title": "Instagram posts for a bakery menu",
        "objective": "Promote the new seasonal menu to local families.",
        "deliverables": ["Three ready-to-post images with captions"],
        "required_skills": ["Canva", "Copywriting"],
        "clarifying_questions": ["Do you have photos of the menu items?"],
        "acceptance_criteria": ["Three images with captions are delivered"],
        "assumptions": ["The bakery already has an Instagram account"],
        "warnings": ["Two days is a short window"],
    },
    "problems": [],
    "validation": [
        {"level": "warning", "message": "Deadline is tight for the scope.", "source": "deterministic"}
    ],
    "raw": "{}",
}


def _find_button(at, label: str):
    for button in at.button:
        if button.label == label:
            return button
    raise AssertionError(f"button not found: {label!r}")


@unittest.skipUnless(AppTest is not None, "streamlit.testing.v1 is not available")
class AppFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        patchers = [
            mock.patch.object(storage, "DATA_DIR", self.data_dir),
            mock.patch.object(storage, "seed_samples_on_first_run", return_value=[]),
            mock.patch.object(gigsie_ai, "generate_task_brief", return_value=FAKE_RESULT),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _open_business(self):
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        _find_button(at, "Start a business request").click().run()
        self.assertFalse(at.exception)
        return at

    @staticmethod
    def _to_passport(at):
        """Create with AI and the Gig Passport are separate pages (Stage 9)."""
        _find_button(at, "Continue to the Gig Passport").click().run()
        return at

    def _fill_request(self, at) -> None:
        at.text_input[0].set_value("Sunrise Bakery")
        at.text_area[0].set_value("Promote our new seasonal menu on Instagram.")
        at.text_area[1].set_value("More local customers visit the shop.")
        at.number_input[0].set_value(800.0)
        at.text_input[1].set_value("2 days")

    def test_landing_renders_without_error(self) -> None:
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        labels = [button.label for button in at.button]
        self.assertIn("Start a business request", labels)
        self.assertIn("Enter the student area", labels)

    def test_business_form_opens(self) -> None:
        at = self._open_business()
        labels = [button.label for button in at.button]
        self.assertIn("Generate task brief", labels)

    def test_invalid_form_is_blocked(self) -> None:
        at = self._open_business()
        # Submit without filling anything: validation must block generation.
        _find_button(at, "Generate task brief").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        # Still on the form - no editor appeared.
        self.assertNotIn("Publish gig", [b.label for b in at.button])

    def test_full_flow_publishes_the_edited_gig(self) -> None:
        at = self._open_business()
        self._fill_request(at)
        _find_button(at, "Generate task brief").click().run()
        self.assertFalse(at.exception)
        self._to_passport(at)

        # The editor is now shown; edit before publishing.
        at.text_input[0].set_value("EDITED bakery menu posts")
        at.text_area[1].set_value("Edited deliverable one\nEdited deliverable two")
        _find_button(at, "Publish gig").click().run()
        self.assertFalse(at.exception)

        published = [g for g in storage.load_gigs(self.data_dir) if not g.get("sample")]
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["title"], "EDITED bakery menu posts")
        self.assertEqual(
            published[0]["brief"]["deliverables"],
            ["Edited deliverable one", "Edited deliverable two"],
        )
        self.assertEqual(published[0]["status"], "open")
        self.assertTrue(any("Published" in s.value for s in at.success))

    def test_rerun_does_not_publish_a_duplicate(self) -> None:
        at = self._open_business()
        self._fill_request(at)
        _find_button(at, "Generate task brief").click().run()
        self._to_passport(at)
        _find_button(at, "Publish gig").click().run()

        # Two extra reruns, as a page refresh would cause.
        at.run()
        at.run()

        published = [g for g in storage.load_gigs(self.data_dir) if not g.get("sample")]
        self.assertEqual(len(published), 1)

    def test_api_failure_shows_error_and_never_publishes(self) -> None:
        with mock.patch.object(
            gigsie_ai,
            "generate_task_brief",
            side_effect=gigsie_ai.GigsieAIError("The model is unavailable right now."),
        ):
            at = self._open_business()
            self._fill_request(at)
            _find_button(at, "Generate task brief").click().run()

            self.assertFalse(at.exception)
            self.assertTrue(at.error)
            # No editor, so nothing could have been published.
            self.assertNotIn("Publish gig", [b.label for b in at.button])
            published = [g for g in storage.load_gigs(self.data_dir) if not g.get("sample")]
            self.assertEqual(published, [])


if __name__ == "__main__":
    unittest.main()
