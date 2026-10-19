"""Tests for the FairScope evaluation harness.

These tests never call Groq. The model boundary is mocked, so the suite spends
no API credit. What is checked here is the *harness*: the dataset is well
formed, the rubric is applied identically to both artefacts, and the evaluation
itself is deterministic given a fixed brief.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fairscope  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
import evaluate_fairscope as harness  # noqa: E402


VAGUE_REQUEST = {
    "project_name": "Meera Wellness Studio",
    "description": "We need help with marketing. Do whatever is needed to get us noticed.",
    "outcome": "More people find us and we get more enquiries and bookings.",
    "budget": 2000,
    "deadline": "",
    "extra_context": "",
}

GOOD_BRIEF = {
    "title": "Three Instagram posts for a bakery's new menu",
    "objective": (
        "Design three square Instagram images and matching captions for the new "
        "seasonal menu at Sunrise Bakery."
    ),
    "deliverables": [
        "Three ready-to-post 1080x1080 images featuring different new menu items",
        "One caption per image written in the bakery's local voice",
    ],
    "required_skills": ["Canva", "Copywriting"],
    "clarifying_questions": ["Do you have photos of the new menu items?"],
    "acceptance_criteria": [
        "Three images of 1080x1080 pixels are delivered",
        "Each image contains a menu item name and price",
    ],
    "assumptions": ["The bakery already has an Instagram business account"],
    "exclusions": ["No paid advertising or boosted posts"],
    "warnings": [],
}

VAGUE_BRIEF = {
    "title": "Marketing help",
    "objective": "Grow the business",
    "deliverables": [],
    "required_skills": [],
    "clarifying_questions": [],
    "acceptance_criteria": [],
    "assumptions": [],
}


class DatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = harness.load_cases()

    def test_the_five_required_scenarios_are_present(self) -> None:
        scenarios = {case["scenario"] for case in self.cases}
        for required in (
            "bakery_social_media",
            "tutor_landing_page",
            "shop_product_descriptions",
            "spreadsheet_cleanup",
            "deliberately_vague_and_over_scoped",
        ):
            self.assertIn(required, scenarios)

    def test_every_case_declares_its_requirements(self) -> None:
        for case in self.cases:
            with self.subTest(case=case.get("id")):
                request = case["request"]
                for field in (
                    "project_name", "description", "outcome", "budget", "deadline"
                ):
                    self.assertIn(field, request)
                self.assertGreater(float(request["budget"]), 0)
                self.assertIn("expect_detection", case)
                self.assertTrue(case["expect_reason"].strip())

    def test_at_least_one_case_is_meant_to_be_detected_as_vague(self) -> None:
        flagged = [case for case in self.cases if case["expect_detection"]]
        self.assertTrue(flagged)
        vague = [
            case
            for case in flagged
            if case["scenario"] == "deliberately_vague_and_over_scoped"
        ]
        self.assertTrue(vague, "the deliberately vague case must expect detection")

    def test_the_dataset_is_labelled_synthetic(self) -> None:
        raw = json.loads(harness.CASES_PATH.read_text(encoding="utf-8"))
        self.assertIn("not real customers", json.dumps(raw).lower())


class RubricTests(unittest.TestCase):
    def test_both_artefacts_use_the_same_measurement_keys(self) -> None:
        case = harness.load_cases()[0]
        row = harness.evaluate_case(case, GOOD_BRIEF)
        shared = (
            "all_required_fields_present", "deliverables_count",
            "deliverables_specific", "criteria_count", "criteria_checkable",
            "budget_preserved", "deadline_preserved",
        )
        for key in shared:
            self.assertIn(key, row["draft"], key)
            self.assertIn(key, row["reviewed"], key)

    def test_artefacts_stay_distinguishable(self) -> None:
        row = harness.evaluate_case(harness.load_cases()[0], GOOD_BRIEF)
        self.assertEqual(row["draft"]["artefact"], "draft")
        self.assertEqual(row["reviewed"]["artefact"], "reviewed")
        self.assertNotEqual(row["draft"], row["reviewed"])

    def test_a_complete_brief_scores_as_structurally_complete(self) -> None:
        request = {
            "project_name": "Sunrise Bakery",
            "description": "Three Instagram images and captions for our new menu.",
            "outcome": "Customers see the new items and visit.",
            "budget": 800,
            "deadline": "2 days",
            "extra_context": "",
        }
        row = harness.evaluate_case(harness.load_cases()[0], GOOD_BRIEF)
        draft = harness.score_draft(request, GOOD_BRIEF)
        self.assertTrue(draft["all_required_fields_present"])
        self.assertEqual(draft["deliverables_count"], 2)
        self.assertTrue(draft["budget_preserved"])
        self.assertTrue(draft["deadline_preserved"])

    def test_vague_deliverables_are_counted_as_not_specific(self) -> None:
        brief = dict(
            GOOD_BRIEF,
            deliverables=["Some posts", "Nice content"],
        )
        draft = harness.score_draft(GOOD_REQUEST := {
            "project_name": "Sunrise Bakery",
            "description": "Posts for the menu.",
            "outcome": "Customers see it.",
            "budget": 800,
            "deadline": "2 days",
        }, brief)
        self.assertEqual(draft["deliverables_count"], 2)
        self.assertLess(draft["deliverables_specific"], 2)
        del GOOD_REQUEST

    def test_missing_deadline_is_never_reported_as_lost(self) -> None:
        """There is nothing to preserve when the business never stated one."""
        draft = harness.score_draft(VAGUE_REQUEST, VAGUE_BRIEF)
        self.assertTrue(draft["deadline_preserved"])

    def test_a_contradictory_budget_in_the_brief_is_caught(self) -> None:
        brief = dict(GOOD_BRIEF, objective="Deliver the work.")
        brief["warnings"] = ["We raised the budget to INR 45000 for this work"]
        draft = harness.score_draft(
            {
                "project_name": "Sunrise Bakery",
                "description": "Three images for the menu.",
                "outcome": "Customers see it.",
                "budget": 800,
                "deadline": "2 days",
            },
            brief,
        )
        self.assertFalse(draft["budget_preserved"])


class DetectionCriterionTests(unittest.TestCase):
    """A warning only counts as correct when the case declared one is expected."""

    def _case(self, expect_detection: bool) -> dict:
        return {
            "id": "case",
            "scenario": "s",
            "note": "",
            "request": VAGUE_REQUEST,
            "expect_detection": expect_detection,
            "expect_reason": "test",
        }

    def test_a_vague_brief_is_detected(self) -> None:
        row = harness.evaluate_case(self._case(True), VAGUE_BRIEF)
        self.assertTrue(row["detection"]["gap_detected"])
        self.assertEqual(row["detection"]["label"], "true_positive")
        self.assertTrue(row["draft"]["clarity_checks_missing"])
        self.assertTrue(row["detection"]["correct"])

    def test_a_specific_brief_is_not_flagged(self) -> None:
        """A genuinely complete brief must not produce a false positive.

        This is the true-negative control: without it, a harness that flagged
        everything would still look perfect.
        """
        case = dict(
            self._case(False),
            request={
                "project_name": "Sunrise Bakery",
                "description": "Three Instagram images and captions for our new menu.",
                "outcome": "Customers see the new items and visit.",
                "budget": 800,
                "deadline": "2 days",
                "extra_context": "We can supply photos of the menu items.",
            },
        )
        complete = dict(
            GOOD_BRIEF,
            title="Instagram posts",
            clarifying_questions=[],
            included_work=[
                "Sizing each image to 1080x1080 and writing one caption per image"
            ],
            exclusions=[
                "No paid advertising or boosted posts",
                "No photography and no ongoing posting schedule",
            ],
            assumptions=["The bakery already has an Instagram business account"],
        )
        row = harness.evaluate_case(case, complete)
        self.assertFalse(
            row["detection"]["gap_detected"],
            f"unexpected gaps: {row['draft']['clarity_checks_missing']}"
            f" {row['draft']['error_level_findings']}",
        )
        # Advisories are expected on real briefs and are never scored.
        self.assertIn("advisories_not_scored", row)
        self.assertEqual(row["detection"]["label"], "true_negative")
        self.assertTrue(row["detection"]["correct"])

    def test_a_deadline_the_brief_never_mentions_is_still_preserved(self) -> None:
        """Preservation means 'not contradicted', not 'echoed by the model'."""
        draft = harness.score_draft(
            {
                "project_name": "Sunrise Bakery",
                "description": "Three images for the menu.",
                "outcome": "Customers see them.",
                "budget": 800,
                "deadline": "2 days",
            },
            dict(GOOD_BRIEF, deliverables=["Images that fit 1080x1080"]),
        )
        self.assertTrue(draft["deadline_preserved"])

    def test_a_brief_that_invents_a_different_deadline_is_caught(self) -> None:
        draft = harness.score_draft(
            {
                "project_name": "Sunrise Bakery",
                "description": "Three images for the menu.",
                "outcome": "Customers see them.",
                "budget": 800,
                "deadline": "2 days",
            },
            dict(
                GOOD_BRIEF,
                deliverables=["Deliver everything within 6 weeks of the request"],
            ),
        )
        self.assertFalse(draft["deadline_preserved"])

    def test_a_case_that_is_not_measured_is_never_a_hit(self) -> None:
        """A model failure must not silently count as a correct detection."""
        row = harness.evaluate_case(
            self._case(True), {}, problems=["model call failed: boom"]
        )
        row["live"] = False
        summary = harness.summarise([row])
        self.assertEqual(summary["cases_measured"], 0)
        self.assertIn("No model-backed results", summary["note"])


class NoApiCallTests(unittest.TestCase):
    def test_the_module_never_calls_the_model_on_import(self) -> None:
        with mock.patch("gigsie_ai.generate_task_brief") as generate:
            import importlib

            importlib.reload(harness)
            generate.assert_not_called()

    def test_self_check_makes_no_model_call(self) -> None:
        with mock.patch("gigsie_ai.generate_task_brief") as generate:
            with mock.patch.object(
                harness, "generate_brief_live", side_effect=AssertionError("no calls")
            ):
                with mock.patch("sys.stdout"):
                    self.assertEqual(harness.run_self_check(), 0)
            generate.assert_not_called()

    def test_live_mode_calls_the_model_exactly_once_per_case(self) -> None:
        cases = harness.load_cases()
        with mock.patch.object(
            harness,
            "generate_brief_live",
            return_value=({"brief": dict(GOOD_BRIEF)}, []),
        ) as live:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "results.json"
                with mock.patch("sys.stdout"):
                    self.assertEqual(harness.run_live(out), 0)
                self.assertEqual(live.call_count, len(cases))
                payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["case_count"], len(cases))
        self.assertIn("structural measurements only", payload["caveat"])

    def test_results_never_contain_a_secret(self) -> None:
        cases = harness.load_cases()
        with mock.patch.object(
            harness, "generate_brief_live", return_value=({"brief": dict(GOOD_BRIEF)}, [])
        ):
            results = []
            for case in cases:
                row = harness.evaluate_case(case, dict(GOOD_BRIEF))
                row["live"] = True
                results.append(row)
        blob = json.dumps(results)
        self.assertNotIn("GROQ_API_KEY", blob)
        self.assertNotIn("sk_", blob)


if __name__ == "__main__":
    unittest.main()
