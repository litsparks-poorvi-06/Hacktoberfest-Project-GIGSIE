"""End-to-end checks for the Streamlit student flow (student_ui.py via app.py).

These use Streamlit's official ``AppTest`` harness to actually run app.py. Storage
is redirected to a temporary folder and the sample seeder is disabled, so your real
``data/`` files are never touched. No AI is called: the student flow is entirely
deterministic.

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

import profiles  # noqa: E402
import storage  # noqa: E402

try:
    from streamlit.testing.v1 import AppTest  # noqa: E402
except Exception:  # pragma: no cover - older Streamlit without the test API
    AppTest = None

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

LONG_PROPOSAL = (
    "I have used Canva for two university projects and I write clear captions, so I "
    "can deliver the three Instagram posts within the two-day window."
)

# One published gig in the schema the business flow actually writes.
GIG = {
    "id": "g_pub0001",
    "title": "Design Instagram posts for a bakery",
    "business_name": "Sunrise Bakery",
    "work_needed": "Promote the new seasonal menu on Instagram.",
    "desired_outcome": "More local customers visit the shop.",
    "budget_inr": 800,
    "deadline": "2 days",
    "additional_context": "",
    "required_skills": ["Canva", "Copywriting"],
    "brief": {
        "objective": "Promote the new menu to local families on Instagram.",
        "deliverables": ["Three Instagram posts with captions"],
        "required_skills": ["Canva", "Copywriting"],
        "clarifying_questions": [],
        "acceptance_criteria": ["Three ready-to-post images with captions"],
        "assumptions": [],
        "warnings": [],
    },
    "status": "open",
    "created_at": "2026-10-15T09:00:00+00:00",
    "sample": False,
}


def _by_label(widgets, label: str):
    for widget in widgets:
        if getattr(widget, "label", None) == label:
            return widget
    raise AssertionError(f"widget with label {label!r} was not found")


def _text(elements) -> str:
    return " ".join(str(getattr(element, "value", "")) for element in elements)


@unittest.skipUnless(AppTest is not None, "streamlit.testing.v1 is not available")
class StudentFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        patchers = [
            mock.patch.object(storage, "DATA_DIR", self.data_dir),
            mock.patch.object(storage, "seed_samples_on_first_run", return_value=[]),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        storage.save_gigs([GIG], data_dir=self.data_dir)

    def _open_student(self):
        """Enter the student area. Stage 9 gives each section its own page."""
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        _by_label(at.button, "Enter the student area").click().run()
        self.assertFalse(at.exception)
        return at

    @staticmethod
    def _open_section(at, label: str):
        """Stage 9: each destination is its own sidebar page."""
        wanted = "".join(ch for ch in label if ch.isalnum()).lower()
        for button in at.sidebar.button:
            text = "".join(ch for ch in button.label if ch.isalnum()).lower()
            if text == wanted:
                button.click().run()
                return at
        raise AssertionError(f"sidebar destination {label!r} was not found")

    def _open_find_work(self):
        """Load the seeded profile, then open the Find Work page."""
        at = self._open_student()
        self._open_section(at, "My Profile")
        _by_label(at.button, "Load this profile").click().run()
        self.assertFalse(at.exception)
        self._open_section(at, "Find Work")
        self.assertFalse(at.exception)
        return at

    def _seed_profile(self, **overrides) -> dict:
        values = {
            "display_name": "Asha Rao",
            "skills": "Canva\nCopywriting",
            "experience_level": "Beginner",
            "bio": "Second-year student.",
            "portfolio_links": ["https://example.com/asha"],
            "weekly_hours": 10,
        }
        values.update(overrides)
        return profiles.save_profile(values, data_dir=self.data_dir)

    # --- rendering --------------------------------------------------------
    def test_student_area_renders(self) -> None:
        at = self._open_student()
        self._open_section(at, "My Profile")
        self.assertIn("Save profile", [b.label for b in at.button])

        # With no profile loaded yet, the apply area asks for a profile instead of
        # showing the proposal form - and no match is invented.
        self._open_section(at, "Find Work")
        self.assertTrue(any("Create a student profile" in i.value for i in at.info))

    def test_empty_state_when_no_gigs(self) -> None:
        (self.data_dir / "gigs.json").unlink()
        at = self._open_student()
        self._open_section(at, "Find Work")
        self.assertTrue(any("No gigs are available" in i.value for i in at.info))

    # --- profile ----------------------------------------------------------
    def test_save_profile_creates_a_local_profile(self) -> None:
        at = self._open_student()
        self._open_section(at, "My Profile")
        _by_label(at.text_input, "Display name *").set_value("Asha Rao")
        _by_label(at.text_area, "Skills (one per line) *").set_value("Canva\nCopywriting")
        _by_label(at.number_input, "Weekly availability (hours per week) *").set_value(12.0)
        _by_label(at.button, "Save profile").click().run()
        self.assertFalse(at.exception)

        saved = storage.load_profiles(self.data_dir)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["display_name"], "Asha Rao")
        self.assertEqual(saved[0]["skills"], ["Canva", "Copywriting"])
        self.assertEqual(saved[0]["weekly_hours"], 12.0)
        self.assertIn("Profile saved", _text(at.success))

    def test_invalid_profile_is_not_saved(self) -> None:
        at = self._open_student()
        self._open_section(at, "My Profile")
        # Submit the blank form: a display name and skills are required.
        _by_label(at.button, "Save profile").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        self.assertEqual(storage.load_profiles(self.data_dir), [])

    def test_loading_a_profile_prefills_the_form(self) -> None:
        self._seed_profile()
        at = self._open_student()
        self._open_section(at, "My Profile")
        _by_label(at.button, "Load this profile").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(_by_label(at.text_input, "Display name *").value, "Asha Rao")

    # --- browse and match -------------------------------------------------
    def test_browse_shows_deterministic_match(self) -> None:
        self._seed_profile()
        at = self._open_find_work()

        markdown = " ".join(m.value for m in at.markdown)
        self.assertIn("Design Instagram posts for a bakery", markdown)
        self.assertIn("Matched required skills", markdown)
        self.assertIn("Canva", markdown)
        # 2 of 2 required skills matched -> 100%.
        self.assertTrue(any(m.value == "100%" for m in at.metric))

    def test_missing_skills_are_explained(self) -> None:
        self._seed_profile(skills="Copywriting")
        at = self._open_find_work()
        markdown = " ".join(m.value for m in at.markdown)
        self.assertIn("Required skills not listed in your profile", markdown)
        self.assertIn("Canva", markdown)

    def test_gig_detail_shows_the_approved_deliverables_and_scope(self) -> None:
        # The student reads the same deliverables and Gig Passport the business
        # approved - no different scope is shown here.
        self._seed_profile()
        at = self._open_find_work()
        markdown = " ".join(m.value for m in at.markdown)
        self.assertIn("Three Instagram posts with captions", markdown)
        self.assertIn("Gig Passport (agreed scope)", " ".join(e.label for e in at.expander))

    # --- applications -----------------------------------------------------
    def _apply(self, at, proposal: str = LONG_PROPOSAL) -> None:
        _by_label(at.text_area, "Your proposal *").set_value(proposal)
        _by_label(at.button, "Review proposal").click().run()
        _by_label(at.button, "Submit application").click().run()

    def test_submit_application_is_saved(self) -> None:
        self._seed_profile()
        at = self._open_find_work()
        self._apply(at)
        self.assertFalse(at.exception)

        saved = storage.load_applications(self.data_dir)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["status"], "submitted")
        self.assertEqual(saved[0]["gig_id"], GIG["id"])
        self.assertEqual(saved[0]["profile_id"], storage.load_profiles(self.data_dir)[0]["id"])

    def test_invalid_proposal_blocks_submission(self) -> None:
        self._seed_profile()
        at = self._open_find_work()
        _by_label(at.text_area, "Your proposal *").set_value("too short")
        _by_label(at.button, "Review proposal").click().run()

        self.assertTrue(at.error)
        _by_label(at.button, "Submit application").click().run()
        self.assertEqual(storage.load_applications(self.data_dir), [])

    def test_duplicate_submission_is_prevented(self) -> None:
        self._seed_profile()
        at = self._open_find_work()
        self._apply(at)

        # Extra reruns, as a page refresh would cause.
        at.run()
        at.run()

        self.assertEqual(len(storage.load_applications(self.data_dir)), 1)
        self.assertTrue(any("already applied" in i.value.lower() for i in at.info))

    def test_proposal_survives_review_and_back(self) -> None:
        self._seed_profile()
        at = self._open_find_work()
        _by_label(at.text_area, "Your proposal *").set_value(LONG_PROPOSAL)
        _by_label(at.button, "Review proposal").click().run()
        _by_label(at.button, "Back to editing").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(_by_label(at.text_area, "Your proposal *").value, LONG_PROPOSAL)

    def test_my_applications_lists_status(self) -> None:
        self._seed_profile()
        at = self._open_find_work()
        self._apply(at)
        self._open_section(at, "My Applications")
        self.assertIn("Submitted", _text(at.markdown))

    # --- business workflow is not affected --------------------------------
    def test_business_workflow_still_reachable(self) -> None:
        at = self._open_student()
        self._open_section(at, "Overview")
        _by_label(at.button, "Start a business request").click().run()
        self.assertFalse(at.exception)
        self.assertIn("Generate task brief", [b.label for b in at.button])

    # --- storage failures fail gracefully ---------------------------------
    def test_gig_storage_failure_is_shown(self) -> None:
        with mock.patch.object(
            storage, "load_gigs", side_effect=storage.StorageError("boom")
        ):
            at = self._open_student()
            self._open_section(at, "Find Work")
            self.assertFalse(at.exception)
            self.assertTrue(any("Gigs could not be read" in e.value for e in at.error))

    def test_profile_storage_failure_is_shown(self) -> None:
        with mock.patch.object(
            storage, "load_profiles", side_effect=storage.StorageError("boom")
        ):
            at = self._open_student()
            self._open_section(at, "My Profile")
            self.assertFalse(at.exception)
            self.assertTrue(
                any("Saved profiles could not be read" in e.value for e in at.error)
            )


if __name__ == "__main__":
    unittest.main()
