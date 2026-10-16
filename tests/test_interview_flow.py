"""End-to-end checks for interview coordination in the Streamlit interfaces.

These use Streamlit's official ``AppTest`` harness to actually run app.py. Storage
is redirected to a temporary folder and the sample seeder is disabled, so your real
``data/`` files are never touched. The AI call is mocked, so no API credits are spent.

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

import applications  # noqa: E402
import gigsie_ai  # noqa: E402
import interviews  # noqa: E402
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

FUTURE = "2999-12-20 15:00"
FUTURE_ALT = "2999-12-21 09:30"
PAST = "2000-01-01 10:00"
GOOD_URL = "https://meet.example.com/abc"
BAD_URL = "meet.example.com/room"

PROFILE_VALUES = {
    "display_name": "Asha Rao",
    "skills": "Canva\nCopywriting",
    "experience_level": "Beginner",
    "bio": "Second-year student.",
    "portfolio_links": ["https://example.com/asha"],
    "weekly_hours": 10,
}

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
    "validation": [],
    "raw": "{}",
}


def _by_label(widgets, label: str):
    for widget in widgets:
        if getattr(widget, "label", None) == label:
            return widget
    raise AssertionError(f"widget with label {label!r} was not found")


def _labels(at) -> list[str]:
    return [button.label for button in at.button]


def _page_text(at) -> str:
    parts = []
    for name in (
        "markdown",
        "caption",
        "text",
        "info",
        "warning",
        "error",
        "success",
        "subheader",
        "header",
    ):
        for element in getattr(at, name, []) or []:
            parts.append(str(getattr(element, "value", "")))
    return "\n".join(parts)


def _success_text(at) -> str:
    return "\n".join(str(element.value) for element in at.success)


@unittest.skipUnless(AppTest is not None, "streamlit.testing.v1 is not available")
class InterviewFlowTests(unittest.TestCase):
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

        storage.save_gigs([GIG], data_dir=self.data_dir)
        self.profile = profiles.save_profile(PROFILE_VALUES, data_dir=self.data_dir)

    # --- helpers -----------------------------------------------------------
    def _open(self, label: str):
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        _by_label(at.button, label).click().run()
        self.assertFalse(at.exception)
        return at

    def _open_business(self):
        return self._open("Start a business request")

    def _open_student(self):
        return self._open("Enter the student area")

    def _open_student_with_profile(self):
        at = self._open_student()
        _by_label(at.button, "Load this profile").click().run()
        self.assertFalse(at.exception)
        return at

    def _seed_application(self, profile: dict | None = None, gig: dict | None = None) -> dict:
        return applications.submit_application(
            profile or self.profile, gig or GIG, LONG_PROPOSAL, data_dir=self.data_dir
        )

    def _seed_interview(
        self, when: str = FUTURE, url: str = "", profile: dict | None = None
    ) -> dict:
        application = self._seed_application(profile=profile)
        return interviews.request_interview(
            application, when, url, data_dir=self.data_dir
        )

    def _interviews(self) -> list[dict]:
        return storage.load_interviews(self.data_dir)

    def _applications(self) -> list[dict]:
        return storage.load_applications(self.data_dir)

    def _fill_interview_request(self, at, when: str = FUTURE, url: str = "") -> None:
        _by_label(
            at.text_input, "Proposed date and time (YYYY-MM-DD HH:MM)"
        ).set_value(when)
        _by_label(at.text_input, "Meeting link (optional)").set_value(url)

    def _apply(self, at) -> None:
        _by_label(at.text_area, "Your proposal *").set_value(LONG_PROPOSAL)
        _by_label(at.button, "Review proposal").click().run()
        self.assertFalse(at.exception)
        _by_label(at.button, "Submit application").click().run()
        self.assertFalse(at.exception)

    # -----------------------------------------------------------------------
    # Phase 1 - business applicants and interview management
    # -----------------------------------------------------------------------
    def test_business_applicant_section_renders(self) -> None:
        self._seed_application()
        at = self._open_business()

        text = _page_text(at)
        self.assertIn("Applicants & interviews", text)
        self.assertIn("Asha Rao", text)
        self.assertIn("Design Instagram posts for a bakery", text)
        # Local demo data must be labelled, with no claim of a verified identity.
        self.assertIn("local demonstration data", text)
        self.assertIn("cannot verify who a business is", text)
        self.assertIn("Submitted", text)
        self.assertIn("Proposal", [e.label for e in at.expander])
        self.assertIn("Student profile", [e.label for e in at.expander])

    def test_business_shows_the_students_portfolio_link(self) -> None:
        self._seed_application()
        at = self._open_business()
        self.assertIn("https://example.com/asha", _page_text(at))

    def test_business_section_when_there_are_no_applications(self) -> None:
        at = self._open_business()
        self.assertTrue(any("No applications yet" in c.value for c in at.caption))

    def test_application_for_an_unknown_gig_is_not_shown(self) -> None:
        # The gig is never saved, so this application is not linked to a real gig
        # and no student/applicant activity may be invented for it.
        self._seed_application(gig={"id": "g_ghost999", "title": "Not saved"})
        at = self._open_business()
        self.assertNotIn("Asha Rao", _page_text(at))
        self.assertTrue(any("No applications yet" in c.value for c in at.caption))

    def test_business_can_shortlist_an_applicant(self) -> None:
        self._seed_application()
        at = self._open_business()
        _by_label(at.button, "Shortlist").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self._applications()[0]["status"], "shortlisted")
        self.assertTrue(any("shortlisted" in s.value.lower() for s in at.success))

    def test_business_can_reject_an_applicant(self) -> None:
        self._seed_application()
        at = self._open_business()
        _by_label(at.button, "Reject").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self._applications()[0]["status"], "rejected")
        self.assertTrue(at.success)

    def test_rejecting_an_application_closes_an_open_interview(self) -> None:
        self._seed_interview()
        at = self._open_business()
        _by_label(at.button, "Reject").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self._applications()[0]["status"], "rejected")
        self.assertEqual(self._interviews()[0]["status"], "declined")

    def test_business_can_request_an_interview(self) -> None:
        self._seed_application()
        at = self._open_business()
        self._fill_interview_request(at, FUTURE, GOOD_URL)
        _by_label(at.button, "Request interview").click().run()
        self.assertFalse(at.exception)

        stored = self._interviews()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["status"], interviews.INTERVIEW_REQUESTED)
        self.assertEqual(stored[0]["requested_datetime"], FUTURE)
        self.assertEqual(stored[0]["meeting_url"], GOOD_URL)
        self.assertEqual(stored[0]["profile_id"], self.profile["id"])
        self.assertEqual(self._applications()[0]["status"], "interview_requested")
        self.assertTrue(any("Interview requested" in s.value for s in at.success))

    def test_business_can_request_an_interview_without_a_link(self) -> None:
        self._seed_application()
        at = self._open_business()
        self._fill_interview_request(at, FUTURE, "")
        _by_label(at.button, "Request interview").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(self._interviews()), 1)
        self.assertEqual(self._interviews()[0]["meeting_url"], "")

    def test_business_cannot_request_an_interview_in_the_past(self) -> None:
        self._seed_application()
        at = self._open_business()
        self._fill_interview_request(at, PAST, "")
        _by_label(at.button, "Request interview").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        self.assertNotIn("Interview requested", _success_text(at))
        self.assertEqual(self._interviews(), [])
        self.assertEqual(self._applications()[0]["status"], "submitted")

    def test_business_cannot_request_an_interview_with_a_bad_link(self) -> None:
        self._seed_application()
        at = self._open_business()
        self._fill_interview_request(at, FUTURE, BAD_URL)
        _by_label(at.button, "Request interview").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        self.assertEqual(self._interviews(), [])

    def test_reruns_do_not_duplicate_interview_requests(self) -> None:
        self._seed_application()
        at = self._open_business()
        self._fill_interview_request(at, FUTURE, "")
        _by_label(at.button, "Request interview").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(self._interviews()), 1)

        # Extra reruns, as a page refresh would cause.
        at.run()
        at.run()
        self.assertEqual(len(self._interviews()), 1)
        # While an interview is open the form is not offered again, so a second
        # click cannot create a duplicate request.
        self.assertNotIn("Request interview", _labels(at))

    def test_business_sees_a_pending_request(self) -> None:
        interview = self._seed_interview()
        at = self._open_business()
        text = _page_text(at)
        self.assertIn("Interview requests & responses", text)
        self.assertIn(interview["requested_datetime"], text)
        self.assertIn("Requested", text)
        self.assertIn("Cancel request", _labels(at))

    def test_business_can_cancel_a_fresh_request(self) -> None:
        self._seed_interview()
        at = self._open_business()
        _by_label(at.button, "Cancel request").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self._interviews()[0]["status"], "declined")
        self.assertEqual(self._applications()[0]["status"], "shortlisted")

    def test_business_can_confirm_an_accepted_interview(self) -> None:
        interview = self._seed_interview(url=GOOD_URL)
        interviews.respond_to_interview(
            interview["id"],
            "accept",
            profile_id=self.profile["id"],
            data_dir=self.data_dir,
        )

        at = self._open_business()
        self.assertIn("Confirm this time", _labels(at))
        _by_label(at.button, "Confirm this time").click().run()
        self.assertFalse(at.exception)

        stored = self._interviews()[0]
        self.assertEqual(stored["status"], interviews.INTERVIEW_CONFIRMED)
        # The final confirmation keeps the agreed time and the meeting link.
        self.assertEqual(stored["confirmed_datetime"], FUTURE)
        self.assertEqual(stored["meeting_url"], GOOD_URL)
        self.assertEqual(self._applications()[0]["status"], "interview_confirmed")

    def test_business_can_confirm_an_alternative_time(self) -> None:
        interview = self._seed_interview()
        interviews.respond_to_interview(
            interview["id"],
            "propose_alternative",
            FUTURE_ALT,
            profile_id=self.profile["id"],
            data_dir=self.data_dir,
        )

        at = self._open_business()
        self.assertIn("Confirm this time", _labels(at))
        self.assertIn(FUTURE_ALT, _page_text(at))
        _by_label(at.button, "Confirm this time").click().run()
        self.assertFalse(at.exception)

        stored = self._interviews()[0]
        self.assertEqual(stored["status"], interviews.INTERVIEW_CONFIRMED)
        self.assertEqual(stored["confirmed_datetime"], FUTURE_ALT)
        self.assertEqual(self._applications()[0]["status"], "interview_confirmed")

    def test_business_view_survives_a_storage_failure(self) -> None:
        self._seed_interview()
        with mock.patch.object(
            storage, "load_interviews", side_effect=storage.StorageError("boom")
        ):
            at = self._open_business()
        self.assertFalse(at.exception)
        self.assertTrue(any("could not be read" in e.value for e in at.error))

    # -----------------------------------------------------------------------
    # Phase 2 - student interview responses
    # -----------------------------------------------------------------------
    def test_student_interview_section_renders(self) -> None:
        interview = self._seed_interview()
        at = self._open_student_with_profile()
        text = _page_text(at)

        self.assertIn("Interviews", text)
        self.assertIn("Design Instagram posts for a bakery", text)
        self.assertIn(interview["requested_datetime"], text)
        self.assertIn("Requested", text)
        self.assertIn("local time", text)
        labels = _labels(at)
        self.assertIn("Accept this time", labels)
        self.assertIn("Decline", labels)
        self.assertIn("Propose this time", labels)

    def test_student_can_accept_a_request(self) -> None:
        self._seed_interview()
        at = self._open_student_with_profile()
        _by_label(at.button, "Accept this time").click().run()
        self.assertFalse(at.exception)

        stored = self._interviews()[0]
        self.assertEqual(stored["status"], interviews.INTERVIEW_ACCEPTED)
        self.assertNotEqual(stored["status"], interviews.INTERVIEW_CONFIRMED)
        self.assertEqual(stored["confirmed_datetime"], "")
        # Still waiting for the business to confirm.
        self.assertEqual(self._applications()[0]["status"], "interview_requested")
        self.assertTrue(
            any("Waiting for the business to confirm" in s.value for s in at.success)
        )

    def test_student_can_decline_a_request(self) -> None:
        self._seed_interview()
        at = self._open_student_with_profile()
        _by_label(at.button, "Decline").click().run()
        self.assertFalse(at.exception)

        self.assertEqual(self._interviews()[0]["status"], interviews.INTERVIEW_DECLINED)
        self.assertEqual(self._applications()[0]["status"], "shortlisted")

    def test_student_can_propose_an_alternative_time(self) -> None:
        self._seed_interview()
        at = self._open_student_with_profile()
        _by_label(
            at.text_input, "Alternative date and time (YYYY-MM-DD HH:MM)"
        ).set_value(FUTURE_ALT)
        _by_label(at.button, "Propose this time").click().run()
        self.assertFalse(at.exception)

        stored = self._interviews()[0]
        self.assertEqual(stored["status"], interviews.INTERVIEW_ALTERNATIVE_PROPOSED)
        self.assertEqual(stored["alternative_datetime"], FUTURE_ALT)
        # Not confirmed until the business agrees.
        self.assertEqual(stored["confirmed_datetime"], "")
        self.assertEqual(self._applications()[0]["status"], "interview_requested")

    def test_student_cannot_propose_a_time_in_the_past(self) -> None:
        self._seed_interview()
        at = self._open_student_with_profile()
        _by_label(
            at.text_input, "Alternative date and time (YYYY-MM-DD HH:MM)"
        ).set_value(PAST)
        _by_label(at.button, "Propose this time").click().run()
        self.assertFalse(at.exception)

        self.assertTrue(at.error)
        # The failed action must not be reported as a success.
        self.assertNotIn("alternative time was sent", _success_text(at))
        stored = self._interviews()[0]
        self.assertEqual(stored["status"], interviews.INTERVIEW_REQUESTED)
        self.assertEqual(stored["alternative_datetime"], "")

    def test_student_sees_an_accepted_request_awaiting_confirmation(self) -> None:
        interview = self._seed_interview()
        interviews.respond_to_interview(
            interview["id"],
            "accept",
            profile_id=self.profile["id"],
            data_dir=self.data_dir,
        )
        at = self._open_student_with_profile()
        self.assertIn(
            "You accepted this time. Waiting for the business to confirm it.",
            _page_text(at),
        )
        # Once accepted the student waits: no second response controls.
        self.assertNotIn("Accept this time", _labels(at))
        self.assertNotIn("Propose this time", _labels(at))

    def test_student_sees_the_final_confirmed_details(self) -> None:
        interview = self._seed_interview(url=GOOD_URL)
        interviews.respond_to_interview(
            interview["id"],
            "accept",
            profile_id=self.profile["id"],
            data_dir=self.data_dir,
        )
        interviews.business_respond(
            interview["id"], "confirm", data_dir=self.data_dir
        )

        at = self._open_student_with_profile()
        text = _page_text(at)
        self.assertIn("This interview is confirmed", text)
        self.assertIn(GOOD_URL, text)
        self.assertIn(FUTURE, text)
        self.assertNotIn("Accept this time", _labels(at))

    def test_student_cannot_respond_to_another_profiles_interview(self) -> None:
        other = {"id": "p_someone_else", "display_name": "Ravi Kumar", "skills": ["Canva"]}
        application = applications.submit_application(
            other, GIG, LONG_PROPOSAL, data_dir=self.data_dir
        )
        interviews.request_interview(application, FUTURE, data_dir=self.data_dir)

        at = self._open_student_with_profile()
        self.assertNotIn("Accept this time", _labels(at))
        self.assertTrue(
            any("No interview requests yet" in i.value for i in at.info)
        )

    def test_student_interviews_require_a_profile(self) -> None:
        self._seed_interview()
        at = self._open_student()
        self.assertNotIn("Accept this time", _labels(at))
        self.assertTrue(
            any("Create or load a profile first" in i.value for i in at.info)
        )

    def test_student_response_storage_failure_shows_an_error(self) -> None:
        self._seed_interview()
        at = self._open_student_with_profile()
        with mock.patch.object(
            storage, "save_interviews", side_effect=storage.StorageError("disk full")
        ):
            _by_label(at.button, "Accept this time").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        # The failed save must not be reported as a success.
        self.assertNotIn("You accepted this time", _success_text(at))
        # The saved state is preserved rather than half-written.
        self.assertEqual(self._interviews()[0]["status"], interviews.INTERVIEW_REQUESTED)

    def test_student_interview_view_survives_a_storage_failure(self) -> None:
        self._seed_interview()
        with mock.patch.object(
            storage, "load_interviews", side_effect=storage.StorageError("boom")
        ):
            at = self._open_student_with_profile()
        self.assertFalse(at.exception)
        self.assertTrue(any("could not be read" in e.value for e in at.error))

    def test_student_interviews_view_is_offered_alongside_the_others(self) -> None:
        at = self._open_student_with_profile()
        labels = [tab.label for tab in at.tabs]
        self.assertEqual(len(labels), 5, labels)
        for expected in (
            "Profile",
            "Browse gigs",
            "My applications",
            "Skill assessments",
            "Interviews",
        ):
            self.assertTrue(any(expected in label for label in labels), labels)
        # The existing sections still render their content too.
        text = _page_text(at)
        self.assertIn("Your student profile", text)
        self.assertIn("Skill assessments", text)

    # -----------------------------------------------------------------------
    # Existing workflows keep working, and assessments never block anything
    # -----------------------------------------------------------------------
    def test_assessments_are_still_accessible(self) -> None:
        at = self._open_student_with_profile()
        self.assertIn("Generate practice assessment", _labels(at))

    def test_assessment_is_not_required_before_applying(self) -> None:
        at = self._open_student_with_profile()
        self._apply(at)
        self.assertEqual(len(self._applications()), 1)
        self.assertEqual(storage.load_assessments(self.data_dir), [])
        self.assertIn("Submitted", _page_text(at))

    def test_existing_student_profile_flow_still_works(self) -> None:
        at = self._open_student()
        _by_label(at.text_input, "Display name *").set_value("Neha Iyer")
        _by_label(at.text_area, "Skills (one per line) *").set_value("Figma")
        _by_label(
            at.number_input, "Weekly availability (hours per week) *"
        ).set_value(12.0)
        _by_label(at.button, "Save profile").click().run()
        self.assertFalse(at.exception)
        saved = storage.load_profiles(self.data_dir)
        self.assertEqual(len(saved), 2)
        self.assertTrue(any(p["display_name"] == "Neha Iyer" for p in saved))

    def test_existing_student_applications_view_still_works(self) -> None:
        at = self._open_student_with_profile()
        self._apply(at)
        self.assertIn("Submitted", _page_text(at))

    def test_existing_business_flow_still_works(self) -> None:
        at = self._open_business()
        at.text_input[0].set_value("Sunrise Bakery")
        at.text_area[0].set_value("Promote our new seasonal menu on Instagram.")
        at.text_area[1].set_value("More local customers visit the shop.")
        at.number_input[0].set_value(800.0)
        at.text_input[1].set_value("2 days")
        _by_label(at.button, "Generate task brief").click().run()
        self.assertFalse(at.exception)
        _by_label(at.button, "Publish gig").click().run()
        self.assertFalse(at.exception)

        published = [g for g in storage.load_gigs(self.data_dir) if not g.get("sample")]
        titles = [g["title"] for g in published]
        self.assertIn("Instagram posts for a bakery menu", titles)
        newest = next(g for g in published if g["title"] == "Instagram posts for a bakery menu")
        self.assertEqual(newest["status"], "open")

    def test_student_can_move_between_business_and_student_views(self) -> None:
        at = self._open_student()
        _by_label(at.button, "← Back to start").click().run()
        self.assertFalse(at.exception)
        _by_label(at.button, "Start a business request").click().run()
        self.assertFalse(at.exception)
        self.assertIn("Generate task brief", _labels(at))


if __name__ == "__main__":
    unittest.main()
