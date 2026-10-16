"""Unit tests for applications.py (proposals, dedupe, and status transitions).

No Streamlit and no API calls: a temporary data folder stands in for the real
``data/`` directory.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import applications  # noqa: E402
import storage  # noqa: E402
import validation  # noqa: E402
from errors import WorkflowError  # noqa: E402

LONG_PROPOSAL = (
    "I have used Canva for two university projects and I can deliver the three "
    "Instagram posts with clear captions within the two-day window."
)


def _profile(profile_id: str = "p_test0001") -> dict:
    return {"id": profile_id, "display_name": "Asha Rao", "skills": ["Canva"]}


def _gig(gig_id: str = "g_test0001") -> dict:
    return {"id": gig_id, "title": "Promote a new bakery menu", "sample": False}


class ProposalValidationTests(unittest.TestCase):
    def test_empty_proposal_is_an_error(self) -> None:
        findings = applications.validate_proposal("")
        self.assertTrue(validation.has_errors(findings))

    def test_short_proposal_is_an_error(self) -> None:
        findings = applications.validate_proposal("too short")
        self.assertTrue(validation.has_errors(findings))

    def test_reasonable_proposal_passes(self) -> None:
        findings = applications.validate_proposal(LONG_PROPOSAL)
        self.assertFalse(validation.has_errors(findings), findings)

    def test_very_long_proposal_is_only_a_warning(self) -> None:
        findings = applications.validate_proposal("x" * (applications.MAX_PROPOSAL_CHARS + 1))
        self.assertFalse(validation.has_errors(findings))
        self.assertTrue(any(f["level"] == "warning" for f in findings))

    def test_non_string_proposal_is_an_error(self) -> None:
        findings = applications.validate_proposal(None)
        self.assertTrue(validation.has_errors(findings))


class StatusTransitionTests(unittest.TestCase):
    def test_allowed_transitions(self) -> None:
        self.assertTrue(
            applications.can_transition(
                applications.STATUS_SUBMITTED, applications.STATUS_SHORTLISTED
            )
        )
        self.assertTrue(
            applications.can_transition(
                applications.STATUS_INTERVIEW_REQUESTED,
                applications.STATUS_INTERVIEW_CONFIRMED,
            )
        )
        self.assertTrue(
            applications.can_transition(
                applications.STATUS_INTERVIEW_CONFIRMED, applications.STATUS_ACCEPTED
            )
        )

    def test_contradictory_transitions_are_blocked(self) -> None:
        self.assertFalse(
            applications.can_transition(
                applications.STATUS_ACCEPTED, applications.STATUS_REJECTED
            )
        )
        self.assertFalse(
            applications.can_transition(
                applications.STATUS_REJECTED, applications.STATUS_ACCEPTED
            )
        )
        # Cannot skip straight from submitted to accepted.
        self.assertFalse(
            applications.can_transition(
                applications.STATUS_SUBMITTED, applications.STATUS_ACCEPTED
            )
        )

    def test_same_status_is_a_safe_noop(self) -> None:
        self.assertTrue(
            applications.can_transition(
                applications.STATUS_SUBMITTED, applications.STATUS_SUBMITTED
            )
        )


class ApplicationWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _submit(self, proposal: str = LONG_PROPOSAL) -> dict:
        return applications.submit_application(
            _profile(), _gig(), proposal, data_dir=self.data_dir
        )

    def test_submission_is_saved_with_submitted_status(self) -> None:
        record = self._submit()
        self.assertEqual(record["status"], applications.STATUS_SUBMITTED)
        self.assertEqual(record["gig_id"], "g_test0001")
        self.assertEqual(record["profile_id"], "p_test0001")
        self.assertEqual(record["student_name"], "Asha Rao")

        stored = storage.load_applications(self.data_dir)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["id"], record["id"])
        self.assertFalse(stored[0]["ai_assisted"])

    def test_duplicate_application_is_rejected(self) -> None:
        first = self._submit()
        with self.assertRaises(WorkflowError) as context:
            self._submit()
        self.assertIn(first["id"], str(context.exception))
        # Still exactly one stored application.
        self.assertEqual(len(storage.load_applications(self.data_dir)), 1)

    def test_duplicate_detection_is_per_profile_and_gig(self) -> None:
        self._submit()
        # A different profile may apply to the same gig.
        applications.submit_application(
            _profile("p_other"), _gig(), LONG_PROPOSAL, data_dir=self.data_dir
        )
        # The same profile may apply to a different gig.
        applications.submit_application(
            _profile(), _gig("g_other"), LONG_PROPOSAL, data_dir=self.data_dir
        )
        self.assertEqual(len(storage.load_applications(self.data_dir)), 3)
        self.assertIsNotNone(
            applications.find_duplicate("p_test0001", "g_test0001", self.data_dir)
        )
        self.assertIsNone(
            applications.find_duplicate("p_test0001", "g_missing", self.data_dir)
        )

    def test_invalid_proposal_is_rejected(self) -> None:
        with self.assertRaises(WorkflowError):
            self._submit("nope")
        self.assertEqual(storage.load_applications(self.data_dir), [])

    def test_missing_profile_or_gig_is_rejected(self) -> None:
        with self.assertRaises(WorkflowError):
            applications.submit_application({}, _gig(), LONG_PROPOSAL, data_dir=self.data_dir)
        with self.assertRaises(WorkflowError):
            applications.submit_application(_profile(), {}, LONG_PROPOSAL, data_dir=self.data_dir)

    def test_applications_are_listed_by_profile_and_gig(self) -> None:
        record = self._submit()
        self.assertEqual(
            [a["id"] for a in applications.applications_for_profile("p_test0001", self.data_dir)],
            [record["id"]],
        )
        self.assertEqual(
            [a["id"] for a in applications.applications_for_gig("g_test0001", self.data_dir)],
            [record["id"]],
        )
        self.assertEqual(applications.applications_for_profile("nobody", self.data_dir), [])
        self.assertEqual(applications.get_application(record["id"], self.data_dir)["id"], record["id"])

    def test_update_status_follows_the_rules(self) -> None:
        record = self._submit()
        shortlisted = applications.update_status(
            record["id"], applications.STATUS_SHORTLISTED, self.data_dir
        )
        self.assertEqual(shortlisted["status"], applications.STATUS_SHORTLISTED)
        self.assertEqual(
            applications.get_application(record["id"], self.data_dir)["status"],
            applications.STATUS_SHORTLISTED,
        )

    def test_update_status_rejects_contradiction(self) -> None:
        record = self._submit()
        applications.update_status(record["id"], applications.STATUS_REJECTED, self.data_dir)
        with self.assertRaises(WorkflowError):
            applications.update_status(record["id"], applications.STATUS_ACCEPTED, self.data_dir)

    def test_update_status_reapplying_same_status_is_noop(self) -> None:
        record = self._submit()
        again = applications.update_status(
            record["id"], applications.STATUS_SUBMITTED, self.data_dir
        )
        self.assertEqual(again["status"], applications.STATUS_SUBMITTED)

    def test_update_status_unknown_id_or_status_raises(self) -> None:
        with self.assertRaises(WorkflowError):
            applications.update_status("a_missing", applications.STATUS_SHORTLISTED, self.data_dir)
        record = self._submit()
        with self.assertRaises(WorkflowError):
            applications.update_status(record["id"], "banana", self.data_dir)

    def test_storage_failure_on_submit_is_reported(self) -> None:
        blocked = Path(self._tmp.name) / "blocked_file"
        blocked.write_text("not a directory", encoding="utf-8")
        with self.assertRaises(storage.StorageError):
            applications.submit_application(_profile(), _gig(), LONG_PROPOSAL, data_dir=blocked)


if __name__ == "__main__":
    unittest.main()
