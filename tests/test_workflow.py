"""Tests for gig_workflow.py - the business flow's deterministic logic.

These tests cover everything the Streamlit layer relies on *without* launching
Streamlit and without any AI or network calls:

    * form validation (budget and deadline are required here),
    * mapping a reviewed brief to the stored gig schema,
    * publishing through storage (always to a temporary folder),
    * preventing duplicate publishes across reruns.

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

import gig_workflow  # noqa: E402
import storage  # noqa: E402
import validation  # noqa: E402


VALID_REQUEST = {
    "project_name": "Sunrise Bakery",
    "description": "Promote our new seasonal menu on Instagram.",
    "outcome": "More local customers visit the shop.",
    "budget": 800,
    "deadline": "2 days",
    "extra_context": "Most customers are nearby families.",
}

VALID_BRIEF = {
    "title": "Instagram posts for a bakery menu",
    "objective": "Promote the new seasonal menu to local families on Instagram.",
    "deliverables": ["Three ready-to-post images with captions"],
    "required_skills": ["Canva", "Copywriting"],
    "clarifying_questions": ["Do you have photos of the menu items?"],
    "acceptance_criteria": ["Three images with captions are delivered"],
    "assumptions": ["The bakery already has an Instagram account"],
    "warnings": ["Two days is a short window if photos still need to be taken"],
}


class TemporaryDataMixin:
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# Form validation
# ---------------------------------------------------------------------------
class ValidateFormTests(TemporaryDataMixin, unittest.TestCase):
    def _errors(self, values):
        return [f for f in gig_workflow.validate_form(values) if f["level"] == "error"]

    def test_complete_form_has_no_errors(self) -> None:
        self.assertEqual(self._errors(VALID_REQUEST), [])

    def test_missing_budget_is_an_error(self) -> None:
        values = dict(VALID_REQUEST, budget=0)
        messages = " ".join(f["message"] for f in self._errors(values))
        self.assertIn("budget", messages.lower())

    def test_missing_deadline_is_an_error(self) -> None:
        values = dict(VALID_REQUEST, deadline="   ")
        messages = " ".join(f["message"] for f in self._errors(values))
        self.assertIn("deadline", messages.lower())

    def test_missing_description_is_an_error(self) -> None:
        values = dict(VALID_REQUEST, description="")
        self.assertTrue(self._errors(values))

    def test_missing_outcome_is_an_error(self) -> None:
        values = dict(VALID_REQUEST, outcome="")
        self.assertTrue(self._errors(values))

    def test_non_dict_input_is_an_error(self) -> None:
        self.assertTrue(self._errors(None))


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
class TextHelperTests(unittest.TestCase):
    def test_split_lines_trims_and_drops_blanks(self) -> None:
        self.assertEqual(
            gig_workflow.split_lines("  one \n\n two\n   \nthree "),
            ["one", "two", "three"],
        )

    def test_split_lines_handles_non_string(self) -> None:
        self.assertEqual(gig_workflow.split_lines(None), [])

    def test_join_lines_round_trips(self) -> None:
        items = ["one", "two"]
        self.assertEqual(gig_workflow.split_lines(gig_workflow.join_lines(items)), items)


# ---------------------------------------------------------------------------
# Building the stored record
# ---------------------------------------------------------------------------
class BuildRecordTests(unittest.TestCase):
    def test_maps_request_and_brief_fields(self) -> None:
        record = gig_workflow.build_gig_record(VALID_BRIEF, VALID_REQUEST)
        self.assertEqual(record["title"], VALID_BRIEF["title"])
        self.assertEqual(record["business_name"], "Sunrise Bakery")
        self.assertEqual(record["work_needed"], VALID_REQUEST["description"])
        self.assertEqual(record["desired_outcome"], VALID_REQUEST["outcome"])
        self.assertEqual(record["budget_inr"], 800.0)
        self.assertEqual(record["deadline"], "2 days")
        self.assertEqual(record["required_skills"], ["Canva", "Copywriting"])

    def test_nested_brief_uses_the_new_schema_keys(self) -> None:
        record = gig_workflow.build_gig_record(VALID_BRIEF, VALID_REQUEST)
        brief = record["brief"]
        self.assertEqual(brief["objective"], VALID_BRIEF["objective"])
        self.assertEqual(brief["deliverables"], VALID_BRIEF["deliverables"])
        self.assertEqual(brief["required_skills"], VALID_BRIEF["required_skills"])
        self.assertEqual(brief["warnings"], VALID_BRIEF["warnings"])

    def test_title_falls_back_to_project_name(self) -> None:
        record = gig_workflow.build_gig_record({"title": ""}, VALID_REQUEST)
        self.assertEqual(record["title"], "Sunrise Bakery")

    def test_title_falls_back_to_untitled(self) -> None:
        record = gig_workflow.build_gig_record({}, {})
        self.assertEqual(record["title"], "Untitled gig")

    def test_string_lists_are_split(self) -> None:
        brief = dict(VALID_BRIEF, deliverables="One\nTwo", required_skills="Canva")
        record = gig_workflow.build_gig_record(brief, VALID_REQUEST)
        self.assertEqual(record["brief"]["deliverables"], ["One", "Two"])
        self.assertEqual(record["required_skills"], ["Canva"])

    def test_new_gig_is_not_a_sample(self) -> None:
        record = gig_workflow.build_gig_record(VALID_BRIEF, VALID_REQUEST)
        self.assertFalse(record["sample"])


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------
class PublishTests(TemporaryDataMixin, unittest.TestCase):
    def test_publish_saves_and_returns_a_gig_id(self) -> None:
        record = gig_workflow.publish_gig(
            VALID_BRIEF, VALID_REQUEST, data_dir=self.data_dir
        )
        self.assertTrue(record["id"].startswith("g_"))
        self.assertEqual(record["status"], "open")

    def test_published_gig_is_retrievable_from_storage(self) -> None:
        record = gig_workflow.publish_gig(
            VALID_BRIEF, VALID_REQUEST, data_dir=self.data_dir
        )
        stored = storage.get_gig(record["id"], self.data_dir)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["title"], VALID_BRIEF["title"])
        self.assertFalse(stored["sample"])

    def test_published_gig_passes_deterministic_validation(self) -> None:
        record = gig_workflow.publish_gig(
            VALID_BRIEF, VALID_REQUEST, data_dir=self.data_dir
        )
        self.assertFalse(validation.has_errors(validation.validate_task(record)))

    def test_published_gig_is_readable_by_the_matcher(self) -> None:
        record = gig_workflow.publish_gig(
            VALID_BRIEF, VALID_REQUEST, data_dir=self.data_dir
        )
        # The student-side matcher must find skills and deliverables.
        self.assertEqual(validation.get_required_skills(record), ["Canva", "Copywriting"])
        self.assertEqual(
            validation.get_deliverables(record),
            ["Three ready-to-post images with captions"],
        )

    def test_publish_without_deliverables_is_rejected_and_not_saved(self) -> None:
        brief = dict(VALID_BRIEF, deliverables=[])
        with self.assertRaises(gig_workflow.PublishError):
            gig_workflow.publish_gig(brief, VALID_REQUEST, data_dir=self.data_dir)
        self.assertEqual(storage.load_gigs(self.data_dir), [])

    def test_storage_failure_raises_publish_error(self) -> None:
        with mock.patch.object(
            storage, "add_gig", side_effect=storage.StorageError("disk full")
        ):
            with self.assertRaises(gig_workflow.PublishError):
                gig_workflow.publish_gig(
                    VALID_BRIEF, VALID_REQUEST, data_dir=self.data_dir
                )


# ---------------------------------------------------------------------------
# Duplicate protection across reruns
# ---------------------------------------------------------------------------
class PublishOnceTests(TemporaryDataMixin, unittest.TestCase):
    def test_same_draft_is_only_published_once(self) -> None:
        state: dict = {}
        first = gig_workflow.publish_once(
            state, "draft-1", VALID_BRIEF, VALID_REQUEST, data_dir=self.data_dir
        )
        second = gig_workflow.publish_once(
            state, "draft-1", VALID_BRIEF, VALID_REQUEST, data_dir=self.data_dir
        )
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(storage.load_gigs(self.data_dir)), 1)

    def test_a_new_draft_can_be_published(self) -> None:
        state: dict = {}
        gig_workflow.publish_once(
            state, "draft-1", VALID_BRIEF, VALID_REQUEST, data_dir=self.data_dir
        )
        second = gig_workflow.publish_once(
            state, "draft-2", VALID_BRIEF, VALID_REQUEST, data_dir=self.data_dir
        )
        self.assertIsNotNone(second)
        self.assertEqual(len(storage.load_gigs(self.data_dir)), 2)

    def test_failed_publish_does_not_mark_the_draft(self) -> None:
        state: dict = {}
        with mock.patch.object(
            storage, "add_gig", side_effect=storage.StorageError("nope")
        ):
            with self.assertRaises(gig_workflow.PublishError):
                gig_workflow.publish_once(
                    state, "draft-1", VALID_BRIEF, VALID_REQUEST, data_dir=self.data_dir
                )
        self.assertNotIn("published_draft_key", state)

    def test_missing_state_is_rejected(self) -> None:
        with self.assertRaises(gig_workflow.PublishError):
            gig_workflow.publish_once(
                None, "draft-1", VALID_BRIEF, VALID_REQUEST, data_dir=self.data_dir
            )


if __name__ == "__main__":
    unittest.main()
