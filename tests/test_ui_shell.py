"""Checks for the redesigned workspace shell (sidebar, home, overviews).

These use Streamlit's official ``AppTest`` harness to run app.py. Storage is
redirected to a temporary folder and the sample sync is mocked, so real
``data/`` files are never touched and no API credits are spent.

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

import storage  # noqa: E402
import ui_common  # noqa: E402

try:
    from streamlit.testing.v1 import AppTest  # noqa: E402
except Exception:  # pragma: no cover - older Streamlit without the test API
    AppTest = None

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

GIG = {
    "id": "g_shell_0001",
    "title": "Design Instagram posts for a bakery",
    "business_name": "Sunrise Bakery",
    "budget_inr": 800,
    "deadline": "2 days",
    "brief": {
        "objective": "Promote the new seasonal menu.",
        "deliverables": ["Three ready-to-post images with captions"],
        "required_skills": ["Canva", "Copywriting"],
        "acceptance_criteria": ["Three ready-to-post images with captions"],
    },
    "status": "open",
    "created_at": "2026-10-15T09:00:00+00:00",
    "sample": False,
}


@unittest.skipUnless(AppTest, "Streamlit AppTest is unavailable")
class UIShellTests(unittest.TestCase):
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

    def _open(self, entry_label: str):
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        for button in at.button:
            if button.label == entry_label:
                button.click().run()
                break
        self.assertFalse(at.exception)
        return at

    def _markdown(self, at) -> str:
        return " ".join(m.value for m in at.markdown)

    def test_home_dashboard_shows_real_cards_and_entry_points(self) -> None:
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.run()
        self.assertFalse(at.exception)

        labels = [button.label for button in at.button]
        self.assertIn("Start a business request", labels)
        self.assertIn("Enter the student area", labels)

        text = self._markdown(at)
        # A workspace, not a wall of disconnected buttons: real summary cards.
        self.assertIn("Your workspace", text)
        self.assertIn("Published gigs", text)
        self.assertIn("Sample gigs", text)

    def test_student_workspace_shows_the_overview_without_a_tab_bar(self) -> None:
        storage.save_gigs([GIG], data_dir=self.data_dir)
        at = self._open("Enter the student area")

        # Stage 9: the sidebar is the only navigation, so no tab bar remains.
        self.assertEqual([tab.label for tab in at.tabs], [])

        text = self._markdown(at)
        self.assertIn("Student Overview", text)
        self.assertIn("Gigs available", text)

    def test_business_workspace_keeps_the_request_form_reachable(self) -> None:
        at = self._open("Start a business request")

        text = self._markdown(at)
        self.assertIn("Create a gig with AI", text)

        # The form is the first thing on the page, so its widgets stay first.
        self.assertEqual(
            at.text_input[0].label, "Business or project name (optional)"
        )
        self.assertEqual(at.number_input[0].label, "Budget in INR *")
        self.assertTrue(any(b.label == "Generate task brief" for b in at.button))


@unittest.skipUnless(AppTest, "Streamlit AppTest is unavailable")
class NavigationTests(unittest.TestCase):
    """The permanent sidebar, section routing, and the header role switch."""

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

    def _run(self, view: str, section: str = ""):
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.session_state["view"] = view
        at.session_state["section"] = section
        at.run()
        self.assertFalse(at.exception)
        return at

    def _markdown(self, at) -> str:
        return " ".join(m.value for m in at.markdown)

    @staticmethod
    def _click_sidebar(at, label: str) -> None:
        """Click a sidebar destination, ignoring the decorative icon prefix."""
        wanted = "".join(ch for ch in label if ch.isalnum()).lower()
        for button in at.sidebar.button:
            text = "".join(ch for ch in button.label if ch.isalnum()).lower()
            if text == wanted:
                button.click().run()
                return
        raise AssertionError(f"sidebar destination {label!r} was not found")

    def test_every_sidebar_destination_is_reachable(self) -> None:
        at = self._run(ui_common.VIEW_HOME)

        labels = [button.label for button in at.sidebar.button]
        for expected in (
            "Overview",
            "Create with AI",
            "Published Gigs",
            "Applicants & Interviews",
            "Find Work",
            "My Profile",
            "My Applications",
            "Skill Assessments",
            "Interviews",
        ):
            self.assertTrue(
                any(expected in label for label in labels),
                f"{expected!r} is missing from the sidebar nav: {labels}",
            )

        # The exact groups specified for the sidebar, and nothing duplicated.
        text = self._markdown(at).upper()
        for group in ("WORKSPACE", "BUSINESS", "STUDENT"):
            self.assertIn(group, text)
        self.assertNotIn("GROW", text)

        # Gig Passport and Student Overview stay real routes but are reached
        # through the workflow, so they are not listed twice at the top level.
        self.assertFalse(any("Gig Passport" in label for label in labels))
        self.assertFalse(any("Student Overview" in label for label in labels))
        self.assertIn("Local prototype", self._markdown(at))

    def test_the_header_carries_no_duplicate_navigation(self) -> None:
        """The sidebar is the only navigation, so the header adds no controls."""
        at = self._run(ui_common.VIEW_HOME)
        header_labels = [button.label for button in at.button]

        self.assertNotIn("← Back to start", header_labels)
        self.assertNotIn("Back to start", header_labels)
        # No Business/Student switch: the sidebar already groups both.
        self.assertEqual(at.segmented_control, [])

    def test_sidebar_navigation_actually_changes_the_page(self) -> None:
        at = self._run(ui_common.VIEW_HOME)
        clicked = False
        for button in at.sidebar.button:
            if "Create with AI" in button.label:
                button.click().run()
                clicked = True
                break
        self.assertTrue(clicked)
        self.assertFalse(at.exception)

        self.assertEqual(at.session_state["view"], ui_common.VIEW_BUSINESS)
        self.assertEqual(at.session_state["section"], ui_common.SEC_CREATE)
        self.assertIn("Create a gig with AI", self._markdown(at))

    def test_each_business_section_renders_its_own_page(self) -> None:
        create = self._run(ui_common.VIEW_BUSINESS, ui_common.SEC_CREATE)
        self.assertIn("Tell us what you need", self._markdown(create))
        self.assertTrue(any(b.label == "Generate task brief" for b in create.button))

        passport = self._run(ui_common.VIEW_BUSINESS, ui_common.SEC_PASSPORT)
        # No draft yet, so the passport page says so instead of showing a form.
        self.assertIn("No draft yet", self._markdown(passport))

        published = self._run(ui_common.VIEW_BUSINESS, ui_common.SEC_PUBLISHED)
        self.assertIn("Published Gigs", self._markdown(published))
        # The published page is where the real search box lives.
        self.assertTrue(any(w.label == "Search" for w in published.text_input))

        applicants = self._run(ui_common.VIEW_BUSINESS, ui_common.SEC_APPLICANTS)
        self.assertIn("Applicants & Interviews", self._markdown(applicants))

    def test_each_student_section_renders_as_its_own_page(self) -> None:
        for section, expected in (
            (ui_common.SEC_FIND_WORK, "Browse published gigs"),
            (ui_common.SEC_PROFILE, "Your student profile"),
            (ui_common.SEC_APPLICATIONS, "Your applications"),
            (ui_common.SEC_ASSESSMENTS, "Skill assessments"),
            (ui_common.SEC_INTERVIEWS, "Interviews"),
        ):
            at = self._run(ui_common.VIEW_STUDENT, section)
            text = self._markdown(at)
            self.assertIn(ui_common.SECTION_LABEL[section], text)
            self.assertIn(expected, text, section)

    def test_navigating_by_role_uses_the_sidebar_only(self) -> None:
        """Moving between the business and student areas is a sidebar click."""
        at = self._run(ui_common.VIEW_HOME)

        self._click_sidebar(at, "Find Work")
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["view"], ui_common.VIEW_STUDENT)
        self.assertEqual(at.session_state["section"], ui_common.SEC_FIND_WORK)

        self._click_sidebar(at, "Create with AI")
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["view"], ui_common.VIEW_BUSINESS)
        self.assertEqual(at.session_state["section"], ui_common.SEC_CREATE)

    def test_student_sections_are_reached_through_the_sidebar(self) -> None:
        at = self._run(ui_common.VIEW_STUDENT, ui_common.SEC_FIND_WORK)

        for label, section in (
            ("My Profile", ui_common.SEC_PROFILE),
            ("My Applications", ui_common.SEC_APPLICATIONS),
            ("Skill Assessments", ui_common.SEC_ASSESSMENTS),
            ("Interviews", ui_common.SEC_INTERVIEWS),
        ):
            wanted = "".join(ch for ch in label if ch.isalnum()).lower()
            for button in at.sidebar.button:
                text = "".join(ch for ch in button.label if ch.isalnum()).lower()
                if text == wanted:
                    button.click().run()
                    break
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state["section"], section, label)
            # The in-page jump bar is gone; the sidebar is the only navigation.
            self.assertEqual([tab.label for tab in at.tabs], [], label)

    def test_overview_shows_an_empty_state_when_nothing_is_saved(self) -> None:
        at = self._run(ui_common.VIEW_HOME)
        self.assertFalse(at.exception)
        self.assertTrue(
            any("could not be read" in e.value for e in at.error) is False
        )
        text = self._markdown(at)
        self.assertIn("Nothing saved on this device yet", text)


@unittest.skipUnless(AppTest, "Streamlit AppTest is unavailable")
class PublishedGigRenderingTests(unittest.TestCase):
    """A real saved gig must read the same way on every page that shows it."""

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

    def _run(self, view: str, section: str = ""):
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.session_state["view"] = view
        at.session_state["section"] = section
        at.run()
        self.assertFalse(at.exception)
        return at

    def _markdown(self, at) -> str:
        return " ".join(m.value for m in at.markdown)

    def test_published_page_renders_the_real_saved_gig(self) -> None:
        at = self._run(ui_common.VIEW_BUSINESS, ui_common.SEC_PUBLISHED)
        text = self._markdown(at)
        self.assertIn("Design Instagram posts for a bakery", text)
        self.assertIn("Sunrise Bakery", text)
        self.assertIn("800 INR", text)
        self.assertIn("Canva", text)

    def test_header_search_filters_real_saved_gigs(self) -> None:
        at = self._run(ui_common.VIEW_HOME)
        at.session_state["gs_search"] = "bakery"
        at.run()
        self.assertFalse(at.exception)
        self.assertIn("Design Instagram posts for a bakery", self._markdown(at))

        at.session_state["gs_search"] = "no-such-gig-anywhere"
        at.run()
        self.assertFalse(at.exception)
        self.assertIn("No saved gig matches that search", self._markdown(at))

    def test_gig_facts_helpers_agree_across_modules(self) -> None:
        # One source of truth: business and student pages read the same values.
        self.assertEqual(ui_common.gig_title(GIG), "Design Instagram posts for a bakery")
        self.assertEqual(ui_common.gig_context(GIG), "Sunrise Bakery")
        self.assertEqual(ui_common.gig_budget(GIG), "800 INR")
        self.assertEqual(ui_common.gig_deadline(GIG), "2 days")
        self.assertEqual(ui_common.gig_skills(GIG), ["Canva", "Copywriting"])
        self.assertEqual(
            ui_common.gig_deliverables(GIG),
            ["Three ready-to-post images with captions"],
        )
        # A gig without a budget never gets a made-up number.
        self.assertEqual(ui_common.gig_budget({"title": "x"}), "Budget not set")

    def test_school_card_markup_is_shared_and_safe(self) -> None:
        card = ui_common.gig_card(GIG)
        self.assertIn("Design Instagram posts for a bakery", card)
        self.assertIn("800 INR", card)
        self.assertIn("Canva", card)

        risky = dict(GIG, title="<script>alert(1)</script>")
        escaped = ui_common.gig_card(risky)
        self.assertNotIn("<script>", escaped)
        self.assertIn("&lt;script&gt;", escaped)


if __name__ == "__main__":
    unittest.main()
