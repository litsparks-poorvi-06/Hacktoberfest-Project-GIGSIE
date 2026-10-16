"""Tests for the Gig Passport gate in the publishing workflow (gig_workflow.py).

These prove that publishing goes through storage exactly as before AND that an
essential, unacknowledged passport gap blocks publication - without inventing
information to pass the check.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fairscope  # noqa: E402
import gig_workflow  # noqa: E402
import storage  # noqa: E402


VALID_REQUEST = {
    "project_name": "Sunrise Bakery",
    "description": "Promote our new seasonal menu on Instagram.",
    "outcome": "More local customers visit the shop.",
    "budget": 800,
    "deadline": "5 days",
    "extra_context": "",
}

COMPLETE_BRIEF = {
    "title": "Instagram posts for a bakery menu",
    "objective": "Promote the new seasonal menu to local families on Instagram.",
    "deliverables": ["Three ready-to-post images with captions"],
    "required_skills": ["Canva", "Copywriting"],
    "clarifying_questions": [],
    "acceptance_criteria": ["Three images with captions are delivered"],
    "assumptions": [],
    "warnings": [],
    "exclusions": ["Paid advertising is not included"],
    "client_responsibilities": ["Provide photos of the menu items"],
    "revision_expectations": ["One round of revisions"],
}


class PassportPublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_complete_gig_is_saved_with_its_passport(self) -> None:
        record = gig_workflow.publish_gig(
            dict(COMPLETE_BRIEF), dict(VALID_REQUEST), data_dir=self.data_dir
        )
        self.assertIn("passport", record)
        self.assertTrue(record["passport"]["sections"])
        saved = storage.load_gigs(self.data_dir)
        self.assertEqual(len(saved), 1)
        self.assertIn("passport", saved[0])

    def test_optional_passport_fields_reach_the_stored_brief(self) -> None:
        record = gig_workflow.publish_gig(
            dict(COMPLETE_BRIEF), dict(VALID_REQUEST), data_dir=self.data_dir
        )
        nested = record["brief"]
        self.assertEqual(nested["exclusions"], ["Paid advertising is not included"])
        self.assertEqual(nested["client_responsibilities"], ["Provide photos of the menu items"])
        self.assertEqual(nested["revision_expectations"], ["One round of revisions"])

    def test_essential_gap_blocks_publishing(self) -> None:
        incomplete = dict(COMPLETE_BRIEF, acceptance_criteria=[], required_skills=[])
        with self.assertRaises(gig_workflow.PublishError):
            gig_workflow.publish_gig(incomplete, dict(VALID_REQUEST), data_dir=self.data_dir)
        self.assertEqual(storage.load_gigs(self.data_dir), [])

    def test_acknowledged_gap_allows_publishing(self) -> None:
        incomplete = dict(COMPLETE_BRIEF, acceptance_criteria=[])
        passport = fairscope.acknowledge(
            fairscope.build_passport(incomplete, VALID_REQUEST), ["definition_of_done"]
        )
        record = gig_workflow.publish_gig(
            incomplete, dict(VALID_REQUEST), data_dir=self.data_dir, passport=passport
        )
        self.assertIn("definition_of_done", record["passport"]["acknowledged"])

    def test_publishing_never_invents_missing_information(self) -> None:
        incomplete = dict(COMPLETE_BRIEF, acceptance_criteria=[])
        passport = fairscope.build_passport(incomplete, VALID_REQUEST)
        self.assertEqual(passport["sections"]["definition_of_done"]["value"], [])

    def test_publish_once_forwards_the_passport(self) -> None:
        state: dict = {}
        passport = fairscope.build_passport(COMPLETE_BRIEF, VALID_REQUEST)
        record = gig_workflow.publish_once(
            state, "draft-1", dict(COMPLETE_BRIEF), dict(VALID_REQUEST),
            data_dir=self.data_dir, passport=passport,
        )
        self.assertIsNotNone(record)
        self.assertEqual(record["passport"]["sections"]["objective"]["value"], COMPLETE_BRIEF["objective"])

    def test_passing_no_passport_still_derives_one(self) -> None:
        record = gig_workflow.build_gig_record(dict(COMPLETE_BRIEF), dict(VALID_REQUEST))
        self.assertTrue(record["passport"]["sections"])


if __name__ == "__main__":
    unittest.main()
