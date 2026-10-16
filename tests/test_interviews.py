"""Unit tests for interviews.py (scheduling, statuses, validation, persistence).

No Streamlit and no API calls: a temporary data folder stands in for the real
``data/`` directory, so your real gigs, profiles, applications, and assessment
results are never touched.

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
import interviews  # noqa: E402
import profiles  # noqa: E402
import storage  # noqa: E402
import validation  # noqa: E402
from errors import WorkflowError  # noqa: E402

LONG_PROPOSAL = (
    "I have used Canva for two university projects and I can deliver the three "
    "Instagram posts with clear captions within the two-day window."
)

FUTURE = "2999-12-20 15:00"
FUTURE_ALT = "2999-12-21 09:30"
PAST = "2000-01-01 10:00"
BAD_URL = "meet.example.com/room"
GOOD_URL = "https://meet.example.com/abc"


def _profile(profile_id: str = "p_test0001") -> dict:
    return {"id": profile_id, "display_name": "Asha Rao", "skills": ["Canva"]}


def _gig(gig_id: str = "g_test0001") -> dict:
    return {"id": gig_id, "title": "Promote a new bakery menu", "sample": False}


def _errors(findings: list[dict]) -> list[str]:
    return [f["message"] for f in findings if f.get("level") == "error"]


class InterviewTestCase(unittest.TestCase):
    """Shared fixture: a temp data folder, a real profile, gig, and application."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        self.profile = profiles.save_profile(
            {
                "display_name": "Asha Rao",
                "skills": "Canva",
                "experience_level": "Beginner",
                "bio": "Second-year student.",
                "portfolio_links": ["https://example.com/asha"],
                "weekly_hours": 10,
            },
            data_dir=self.data_dir,
        )
        self.gig = _gig()
        self.application = applications.submit_application(
            self.profile, self.gig, LONG_PROPOSAL, data_dir=self.data_dir
        )

    # -- helpers ------------------------------------------------------------
    def _app(self) -> dict | None:
        """Reload the application from disk (its status changes as we act)."""
        return applications.get_application(self.application["id"], self.data_dir)

    def _request(self, when: str = FUTURE, url: str = "") -> dict:
        return interviews.request_interview(
            self._app(), when, url, data_dir=self.data_dir
        )

    def _accepted(self) -> dict:
        """Request an interview and have the student accept it (awaiting confirmation)."""
        interview = self._request()
        interviews.respond_to_interview(
            interview["id"], "accept", profile_id=self.profile["id"], data_dir=self.data_dir
        )
        return interview

    def _stored_interviews(self) -> list[dict]:
        return storage.load_interviews(self.data_dir)


class ValidationTests(InterviewTestCase):
    # --- date and time -----------------------------------------------------
    def test_datetime_is_required(self) -> None:
        self.assertTrue(_errors(interviews.validate_datetime("")))

    def test_unparseable_datetime_is_an_error(self) -> None:
        self.assertTrue(_errors(interviews.validate_datetime("sometime next week")))

    def test_past_datetime_is_rejected(self) -> None:
        findings = interviews.validate_datetime(PAST)
        self.assertTrue(_errors(findings))
        self.assertTrue(any("past" in m for m in _errors(findings)))

    def test_future_datetime_is_accepted(self) -> None:
        self.assertEqual(_errors(interviews.validate_datetime(FUTURE)), [])

    def test_future_datetime_with_timezone_is_accepted(self) -> None:
        # A timezone-aware value must not crash the naive/aware comparison.
        self.assertEqual(
            _errors(interviews.validate_datetime("2999-12-20T15:00:00+00:00")), []
        )

    def test_past_datetime_with_timezone_is_rejected(self) -> None:
        self.assertTrue(_errors(interviews.validate_datetime("2000-01-01T10:00:00+05:30")))

    def test_datetime_iso_t_format_is_accepted(self) -> None:
        self.assertEqual(_errors(interviews.validate_datetime("2999-12-20T15:00:00")), [])

    def test_normalize_datetime_keeps_local_wall_clock(self) -> None:
        self.assertEqual(interviews.normalize_datetime(FUTURE), "2999-12-20 15:00")

    def test_normalize_datetime_returns_original_text_when_unusable(self) -> None:
        self.assertEqual(interviews.normalize_datetime("next tuesday"), "next tuesday")

    def test_local_timezone_label_names_the_zone(self) -> None:
        label = interviews.local_timezone_label()
        self.assertTrue(label)
        self.assertIn("UTC", label)

    # --- meeting link ------------------------------------------------------
    def test_meeting_url_is_optional(self) -> None:
        self.assertEqual(interviews.validate_meeting_url(""), [])
        self.assertEqual(interviews.validate_meeting_url(None), [])

    def test_valid_meeting_url_is_accepted(self) -> None:
        self.assertEqual(interviews.validate_meeting_url(GOOD_URL), [])

    def test_meeting_url_without_scheme_is_rejected(self) -> None:
        self.assertTrue(_errors(interviews.validate_meeting_url(BAD_URL)))

    def test_non_http_meeting_url_is_rejected(self) -> None:
        self.assertTrue(_errors(interviews.validate_meeting_url("ftp://example.com/x")))

    def test_interview_request_findings_combine_date_and_url(self) -> None:
        findings = interviews.validate_interview_request(PAST, BAD_URL)
        self.assertEqual(len(_errors(findings)), 2)


class RequestInterviewTests(InterviewTestCase):
    def test_request_creates_a_requested_interview(self) -> None:
        interview = self._request()
        self.assertEqual(interview["status"], interviews.INTERVIEW_REQUESTED)
        self.assertEqual(len(self._stored_interviews()), 1)

    def test_request_links_application_gig_and_profile(self) -> None:
        interview = self._request()
        self.assertEqual(interview["application_id"], self.application["id"])
        self.assertEqual(interview["gig_id"], self.gig["id"])
        self.assertEqual(interview["profile_id"], self.profile["id"])
        self.assertEqual(interview["student_name"], "Asha Rao")
        self.assertTrue(interview["id"].startswith("i_"))

    def test_request_record_has_timestamps_and_schedule_fields(self) -> None:
        interview = self._request()
        for field in (
            "id",
            "application_id",
            "gig_id",
            "student_name",
            "requested_datetime",
            "alternative_datetime",
            "confirmed_datetime",
            "meeting_url",
            "status",
            "created_at",
            "updated_at",
        ):
            self.assertIn(field, interview)
        self.assertEqual(interview["requested_datetime"], FUTURE)
        self.assertTrue(interview["created_at"])
        self.assertTrue(interview["updated_at"])

    def test_request_moves_application_to_interview_requested(self) -> None:
        self._request()
        self.assertEqual(self._app()["status"], applications.STATUS_INTERVIEW_REQUESTED)

    def test_request_without_meeting_url_is_allowed(self) -> None:
        interview = self._request(url="")
        self.assertEqual(interview["meeting_url"], "")

    def test_request_records_the_meeting_url(self) -> None:
        interview = self._request(url=GOOD_URL)
        self.assertEqual(interview["meeting_url"], GOOD_URL)

    def test_request_rejects_a_past_datetime_and_saves_nothing(self) -> None:
        with self.assertRaises(WorkflowError):
            self._request(when=PAST)
        self.assertEqual(self._stored_interviews(), [])
        self.assertEqual(self._app()["status"], applications.STATUS_SUBMITTED)

    def test_request_rejects_an_invalid_meeting_url(self) -> None:
        with self.assertRaises(WorkflowError):
            self._request(url=BAD_URL)
        self.assertEqual(self._stored_interviews(), [])
        self.assertEqual(self._app()["status"], applications.STATUS_SUBMITTED)

    def test_request_needs_a_readable_application(self) -> None:
        with self.assertRaises(WorkflowError):
            interviews.request_interview(
                {"title": "no id"}, FUTURE, data_dir=self.data_dir
            )
        self.assertEqual(self._stored_interviews(), [])

    def test_request_is_only_for_an_eligible_application(self) -> None:
        applications.update_status(
            self.application["id"], applications.STATUS_REJECTED, self.data_dir
        )
        with self.assertRaises(WorkflowError):
            self._request()
        self.assertEqual(self._stored_interviews(), [])

    def test_accepted_application_cannot_get_an_interview(self) -> None:
        applications.update_status(
            self.application["id"], applications.STATUS_SHORTLISTED, self.data_dir
        )
        applications.update_status(
            self.application["id"], applications.STATUS_ACCEPTED, self.data_dir
        )
        with self.assertRaises(WorkflowError):
            self._request()
        self.assertEqual(self._stored_interviews(), [])

    def test_duplicate_open_request_is_blocked(self) -> None:
        self._request()
        with self.assertRaises(WorkflowError):
            self._request()
        self.assertEqual(len(self._stored_interviews()), 1)

    def test_reruns_do_not_create_duplicate_requests(self) -> None:
        # Streamlit can fire the same click more than once across reruns.
        self._request()
        for _ in range(3):
            with self.assertRaises(WorkflowError):
                self._request()
        self.assertEqual(len(self._stored_interviews()), 1)
        self.assertEqual(self._app()["status"], applications.STATUS_INTERVIEW_REQUESTED)

    def test_declined_interview_does_not_block_a_new_request(self) -> None:
        first = self._request()
        interviews.respond_to_interview(
            first["id"], "decline", profile_id=self.profile["id"], data_dir=self.data_dir
        )
        second = self._request()
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(self._stored_interviews()), 2)


class StudentResponseTests(InterviewTestCase):
    def test_accept_moves_to_accepted_and_not_confirmed(self) -> None:
        interview = self._request()
        result = interviews.respond_to_interview(
            interview["id"],
            "accept",
            profile_id=self.profile["id"],
            data_dir=self.data_dir,
        )
        self.assertEqual(result["status"], interviews.INTERVIEW_ACCEPTED)
        self.assertNotEqual(result["status"], interviews.INTERVIEW_CONFIRMED)
        self.assertEqual(result["confirmed_datetime"], "")

    def test_accept_keeps_the_application_awaiting_confirmation(self) -> None:
        interview = self._request()
        interviews.respond_to_interview(
            interview["id"],
            "accept",
            profile_id=self.profile["id"],
            data_dir=self.data_dir,
        )
        self.assertEqual(
            self._app()["status"], applications.STATUS_INTERVIEW_REQUESTED
        )

    def test_decline_closes_the_request_and_requeues_the_application(self) -> None:
        interview = self._request()
        result = interviews.respond_to_interview(
            interview["id"],
            "decline",
            profile_id=self.profile["id"],
            data_dir=self.data_dir,
        )
        self.assertEqual(result["status"], interviews.INTERVIEW_DECLINED)
        self.assertEqual(self._app()["status"], applications.STATUS_SHORTLISTED)

    def test_alternative_time_is_stored_with_its_own_status(self) -> None:
        interview = self._request()
        result = interviews.respond_to_interview(
            interview["id"],
            "propose_alternative",
            FUTURE_ALT,
            profile_id=self.profile["id"],
            data_dir=self.data_dir,
        )
        self.assertEqual(result["status"], interviews.INTERVIEW_ALTERNATIVE_PROPOSED)
        self.assertEqual(result["alternative_datetime"], FUTURE_ALT)
        # Not confirmed until the business agrees.
        self.assertEqual(result["confirmed_datetime"], "")

    def test_alternative_time_cannot_be_in_the_past(self) -> None:
        interview = self._request()
        with self.assertRaises(WorkflowError):
            interviews.respond_to_interview(
                interview["id"],
                "propose_alternative",
                PAST,
                profile_id=self.profile["id"],
                data_dir=self.data_dir,
            )
        stored = self._stored_interviews()[0]
        self.assertEqual(stored["status"], interviews.INTERVIEW_REQUESTED)
        self.assertEqual(stored["alternative_datetime"], "")

    def test_a_different_profile_cannot_respond(self) -> None:
        interview = self._request()
        with self.assertRaises(WorkflowError):
            interviews.respond_to_interview(
                interview["id"], "accept", profile_id="p_someone_else", data_dir=self.data_dir
            )
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_REQUESTED
        )

    def test_unknown_interview_is_rejected(self) -> None:
        with self.assertRaises(WorkflowError):
            interviews.respond_to_interview(
                "i_missing", "accept", profile_id=self.profile["id"], data_dir=self.data_dir
            )

    def test_student_cannot_use_a_business_only_action(self) -> None:
        interview = self._request()
        with self.assertRaises(WorkflowError):
            interviews.respond_to_interview(
                interview["id"], "confirm", profile_id=self.profile["id"], data_dir=self.data_dir
            )
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_REQUESTED
        )

    def test_student_cannot_answer_twice(self) -> None:
        interview = self._request()
        interviews.respond_to_interview(
            interview["id"], "accept", profile_id=self.profile["id"], data_dir=self.data_dir
        )
        with self.assertRaises(WorkflowError):
            interviews.respond_to_interview(
                interview["id"],
                "propose_alternative",
                FUTURE_ALT,
                profile_id=self.profile["id"],
                data_dir=self.data_dir,
            )
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_ACCEPTED
        )

    def test_declined_request_cannot_be_accepted_afterwards(self) -> None:
        interview = self._request()
        interviews.respond_to_interview(
            interview["id"], "decline", profile_id=self.profile["id"], data_dir=self.data_dir
        )
        with self.assertRaises(WorkflowError):
            interviews.respond_to_interview(
                interview["id"], "accept", profile_id=self.profile["id"], data_dir=self.data_dir
            )
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_DECLINED
        )


class BusinessResponseTests(InterviewTestCase):
    def test_confirm_from_accepted_keeps_the_agreed_time_and_url(self) -> None:
        interview = self._request(url=GOOD_URL)
        interviews.respond_to_interview(
            interview["id"], "accept", profile_id=self.profile["id"], data_dir=self.data_dir
        )
        result = interviews.business_respond(
            interview["id"], "confirm", data_dir=self.data_dir
        )
        self.assertEqual(result["status"], interviews.INTERVIEW_CONFIRMED)
        self.assertEqual(result["confirmed_datetime"], FUTURE)
        self.assertEqual(result["requested_datetime"], FUTURE)
        self.assertEqual(result["meeting_url"], GOOD_URL)

    def test_confirm_from_alternative_uses_the_alternative_time(self) -> None:
        interview = self._request()
        interviews.respond_to_interview(
            interview["id"],
            "propose_alternative",
            FUTURE_ALT,
            profile_id=self.profile["id"],
            data_dir=self.data_dir,
        )
        result = interviews.business_respond(
            interview["id"], "confirm", data_dir=self.data_dir
        )
        self.assertEqual(result["status"], interviews.INTERVIEW_CONFIRMED)
        self.assertEqual(result["confirmed_datetime"], FUTURE_ALT)

    def test_confirm_sets_the_application_to_interview_confirmed(self) -> None:
        interview = self._accepted()
        interviews.business_respond(interview["id"], "confirm", data_dir=self.data_dir)
        self.assertEqual(
            self._app()["status"], applications.STATUS_INTERVIEW_CONFIRMED
        )

    def test_legacy_accept_alternative_alias_still_works(self) -> None:
        interview = self._request()
        interviews.respond_to_interview(
            interview["id"],
            "propose_alternative",
            FUTURE_ALT,
            profile_id=self.profile["id"],
            data_dir=self.data_dir,
        )
        result = interviews.business_respond(
            interview["id"], "accept_alternative", data_dir=self.data_dir
        )
        self.assertEqual(result["status"], interviews.INTERVIEW_CONFIRMED)
        self.assertEqual(result["confirmed_datetime"], FUTURE_ALT)

    def test_business_decline_closes_an_accepted_request(self) -> None:
        interview = self._accepted()
        result = interviews.business_respond(
            interview["id"], "decline", data_dir=self.data_dir
        )
        self.assertEqual(result["status"], interviews.INTERVIEW_DECLINED)
        self.assertEqual(result["confirmed_datetime"], "")
        self.assertEqual(self._app()["status"], applications.STATUS_SHORTLISTED)

    def test_legacy_decline_alternative_alias_still_works(self) -> None:
        interview = self._request()
        interviews.respond_to_interview(
            interview["id"],
            "propose_alternative",
            FUTURE_ALT,
            profile_id=self.profile["id"],
            data_dir=self.data_dir,
        )
        result = interviews.business_respond(
            interview["id"], "decline_alternative", data_dir=self.data_dir
        )
        self.assertEqual(result["status"], interviews.INTERVIEW_DECLINED)

    def test_business_can_cancel_a_fresh_request(self) -> None:
        interview = self._request()
        result = interviews.business_respond(
            interview["id"], "cancel", data_dir=self.data_dir
        )
        self.assertEqual(result["status"], interviews.INTERVIEW_DECLINED)
        self.assertEqual(self._app()["status"], applications.STATUS_SHORTLISTED)

    def test_cannot_confirm_before_the_student_answers(self) -> None:
        interview = self._request()
        with self.assertRaises(WorkflowError):
            interviews.business_respond(interview["id"], "confirm", data_dir=self.data_dir)
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_REQUESTED
        )

    def test_a_declined_request_cannot_be_confirmed(self) -> None:
        interview = self._request()
        interviews.respond_to_interview(
            interview["id"], "decline", profile_id=self.profile["id"], data_dir=self.data_dir
        )
        with self.assertRaises(WorkflowError):
            interviews.business_respond(interview["id"], "confirm", data_dir=self.data_dir)
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_DECLINED
        )

    def test_a_confirmed_interview_cannot_be_cancelled(self) -> None:
        interview = self._accepted()
        interviews.business_respond(interview["id"], "confirm", data_dir=self.data_dir)
        with self.assertRaises(WorkflowError):
            interviews.business_respond(interview["id"], "cancel", data_dir=self.data_dir)
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_CONFIRMED
        )

    def test_business_cannot_use_a_student_only_action(self) -> None:
        interview = self._request()
        with self.assertRaises(WorkflowError):
            interviews.business_respond(interview["id"], "accept", data_dir=self.data_dir)
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_REQUESTED
        )

    def test_unknown_interview_is_rejected(self) -> None:
        with self.assertRaises(WorkflowError):
            interviews.business_respond("i_missing", "confirm", data_dir=self.data_dir)

    def test_confirmation_keeps_the_application_history_consistent(self) -> None:
        interview = self._accepted()
        interviews.business_respond(interview["id"], "confirm", data_dir=self.data_dir)
        stored = self._stored_interviews()[0]
        actions = [entry["action"] for entry in stored["history"]]
        self.assertEqual(actions, ["request_interview", "accept", "confirm"])
        actors = [entry["actor"] for entry in stored["history"]]
        self.assertEqual(actors, ["business", "student", "business"])


class ContradictoryStateTests(InterviewTestCase):
    def test_interview_cannot_change_once_the_application_is_rejected(self) -> None:
        interview = self._request()
        applications.update_status(
            self.application["id"], applications.STATUS_REJECTED, self.data_dir
        )
        with self.assertRaises(WorkflowError):
            interviews.respond_to_interview(
                interview["id"], "accept", profile_id=self.profile["id"], data_dir=self.data_dir
            )
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_REQUESTED
        )

    def test_interview_cannot_change_once_the_application_is_accepted(self) -> None:
        interview = self._request()
        applications.update_status(
            self.application["id"],
            applications.STATUS_SHORTLISTED,
            self.data_dir,
        )
        applications.update_status(
            self.application["id"], applications.STATUS_ACCEPTED, self.data_dir
        )
        with self.assertRaises(WorkflowError):
            interviews.business_respond(interview["id"], "cancel", data_dir=self.data_dir)
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_REQUESTED
        )

    def test_interview_without_a_matching_application_is_rejected(self) -> None:
        interview = self._request()
        storage.save_applications([], data_dir=self.data_dir)
        with self.assertRaises(WorkflowError):
            interviews.respond_to_interview(
                interview["id"], "accept", profile_id=self.profile["id"], data_dir=self.data_dir
            )
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_REQUESTED
        )

    def test_rejecting_an_application_closes_an_open_interview(self) -> None:
        interview = self._request()
        applications.update_status(
            self.application["id"], applications.STATUS_REJECTED, self.data_dir
        )
        interviews.decline_open_interviews_for_application(
            self.application["id"], data_dir=self.data_dir
        )
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_DECLINED
        )

    def test_closing_leaves_already_closed_interviews_untouched(self) -> None:
        interview = self._request()
        interviews.respond_to_interview(
            interview["id"], "decline", profile_id=self.profile["id"], data_dir=self.data_dir
        )
        closed_before = self._stored_interviews()[0]
        interviews.decline_open_interviews_for_application(
            self.application["id"], data_dir=self.data_dir
        )
        closed_after = self._stored_interviews()[0]
        self.assertEqual(closed_before["history"], closed_after["history"])

    def test_closing_does_not_touch_other_applications(self) -> None:
        self._request()
        other = applications.submit_application(
            _profile("p_other0001"), _gig("g_other0001"), LONG_PROPOSAL, data_dir=self.data_dir
        )
        interviews.decline_open_interviews_for_application(
            other["id"], data_dir=self.data_dir
        )
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_REQUESTED
        )


class PersistenceTests(InterviewTestCase):
    def test_interview_survives_a_storage_reload(self) -> None:
        interview = self._request(url=GOOD_URL)
        reloaded = interviews.get_interview(interview["id"], self.data_dir)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["status"], interviews.INTERVIEW_REQUESTED)
        self.assertEqual(reloaded["meeting_url"], GOOD_URL)

    def test_status_change_survives_a_storage_reload(self) -> None:
        interview = self._accepted()
        reloaded = interviews.get_interview(interview["id"], self.data_dir)
        self.assertEqual(reloaded["status"], interviews.INTERVIEW_ACCEPTED)

    def test_interviews_are_filtered_by_profile(self) -> None:
        self._request()
        self.assertEqual(
            interviews.interviews_for_profile("p_someone_else", self.data_dir), []
        )
        mine = interviews.interviews_for_profile(self.profile["id"], self.data_dir)
        self.assertEqual(len(mine), 1)

    def test_interviews_are_filtered_by_gig(self) -> None:
        self._request()
        self.assertEqual(interviews.interviews_for_gigs([], self.data_dir), [])
        self.assertEqual(len(interviews.interviews_for_gigs([self.gig["id"]], self.data_dir)), 1)

    def test_active_interview_excludes_declined(self) -> None:
        interview = self._request()
        self.assertIsNotNone(
            interviews.active_interview_for_application(
                self.application["id"], self.data_dir
            )
        )
        interviews.respond_to_interview(
            interview["id"], "decline", profile_id=self.profile["id"], data_dir=self.data_dir
        )
        self.assertIsNone(
            interviews.active_interview_for_application(
                self.application["id"], self.data_dir
            )
        )

    def test_reading_interviews_when_nothing_is_saved(self) -> None:
        self.assertEqual(storage.load_interviews(self.data_dir), [])
        self.assertIsNone(
            interviews.active_interview_for_application("a_missing", self.data_dir)
        )
        self.assertEqual(interviews.interviews_for_profile("p_x", self.data_dir), [])


class StorageFailureTests(InterviewTestCase):
    def test_request_failure_preserves_previous_records(self) -> None:
        with mock.patch.object(
            storage, "save_interviews", side_effect=storage.StorageError("disk full")
        ):
            with self.assertRaises(storage.StorageError):
                self._request()
        self.assertEqual(storage.load_interviews(self.data_dir), [])
        # The application status must not have moved to "interview requested"
        # for an interview that was never saved.
        self.assertEqual(self._app()["status"], applications.STATUS_SUBMITTED)

    def test_student_response_failure_preserves_previous_state(self) -> None:
        interview = self._request()
        with mock.patch.object(
            storage, "save_interviews", side_effect=storage.StorageError("disk full")
        ):
            with self.assertRaises(storage.StorageError):
                interviews.respond_to_interview(
                    interview["id"],
                    "accept",
                    profile_id=self.profile["id"],
                    data_dir=self.data_dir,
                )
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_REQUESTED
        )
        self.assertEqual(
            self._app()["status"], applications.STATUS_INTERVIEW_REQUESTED
        )

    def test_business_response_failure_preserves_previous_state(self) -> None:
        interview = self._accepted()
        with mock.patch.object(
            storage, "save_interviews", side_effect=storage.StorageError("disk full")
        ):
            with self.assertRaises(storage.StorageError):
                interviews.business_respond(
                    interview["id"], "confirm", data_dir=self.data_dir
                )
        self.assertEqual(
            self._stored_interviews()[0]["status"], interviews.INTERVIEW_ACCEPTED
        )
        self.assertEqual(
            self._app()["status"], applications.STATUS_INTERVIEW_REQUESTED
        )

    def test_invalid_input_is_reported_before_any_write(self) -> None:
        with self.assertRaises(WorkflowError):
            self._request(when=PAST)
        self.assertEqual(storage.load_interviews(self.data_dir), [])
        self.assertEqual(storage.load_applications(self.data_dir), [self._app()])


class StatusDefinitionTests(InterviewTestCase):
    def test_lifecycle_statuses_are_defined(self) -> None:
        for status in (
            "requested",
            "accepted",
            "alternative_proposed",
            "confirmed",
            "declined",
        ):
            self.assertIn(status, interviews.INTERVIEW_STATUSES)
            self.assertTrue(interviews.INTERVIEW_STATUS_LABELS.get(status))

    def test_pending_statuses_are_the_ones_needing_a_business_reply(self) -> None:
        self.assertEqual(
            set(interviews.PENDING_BUSINESS_STATUSES),
            {"requested", "accepted", "alternative_proposed"},
        )

    def test_student_cannot_act_on_a_confirmed_interview(self) -> None:
        interview = self._accepted()
        interviews.business_respond(interview["id"], "confirm", data_dir=self.data_dir)
        with self.assertRaises(WorkflowError):
            interviews.respond_to_interview(
                interview["id"], "accept", profile_id=self.profile["id"], data_dir=self.data_dir
            )

    def test_interview_status_labels_cover_every_status(self) -> None:
        for status in interviews.INTERVIEW_STATUSES:
            self.assertIn(status, interviews.INTERVIEW_STATUS_LABELS)
        for action in interviews.STUDENT_ACTIONS:
            self.assertTrue(interviews.STUDENT_ACTIONS[action])
        for action in interviews.BUSINESS_ACTIONS:
            self.assertTrue(interviews.BUSINESS_ACTIONS[action])

    def test_application_status_rules_still_hold(self) -> None:
        # Rejections remain allowed from every non-terminal state.
        for status in (
            applications.STATUS_SUBMITTED,
            applications.STATUS_SHORTLISTED,
            applications.STATUS_INTERVIEW_REQUESTED,
            applications.STATUS_INTERVIEW_CONFIRMED,
        ):
            self.assertTrue(
                applications.can_transition(status, applications.STATUS_REJECTED)
            )
        self.assertFalse(
            applications.can_transition(
                applications.STATUS_REJECTED, applications.STATUS_SHORTLISTED
            )
        )

    def test_validation_module_is_still_healthy(self) -> None:
        self.assertFalse(validation.has_errors([]))


if __name__ == "__main__":
    unittest.main()
