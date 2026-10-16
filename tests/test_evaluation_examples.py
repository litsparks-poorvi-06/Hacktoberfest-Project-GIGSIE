"""FairScope evaluation examples (illustrative, not real customers).

Three small tasks a beginner freelancer might accept:

  1. a bakery wanting Instagram promotion for a small budget and two days,
  2. a tutor wanting a one-page website,
  3. a shop wanting product-listing descriptions.

These tests use FairScope directly (no model, no network). They check that:

  * an overbroad request is flagged as a reason to review,
  * a narrowed version states verifiable outputs,
  * the original budget and deadline are preserved verbatim,
  * missing information is flagged honestly rather than invented,
  * the reviewer is never given a numeric feasibility score or a guarantee.

They do NOT claim the model beats any other model - that would need a comparative
evaluation we have not run.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fairscope  # noqa: E402


BAKERY_REQUEST = {
    "project_name": "Sunrise Bakery",
    "description": "Manage all our marketing and grow everything on Instagram.",
    "outcome": "Become the best-known bakery in the city.",
    "budget": 800,
    "deadline": "2 days",
}

BAKERY_BROAD_BRIEF = {
    "title": "Full social media management",
    "objective": "Handle our entire Instagram presence and grow the account.",
    "deliverables": [
        "Daily posts",
        "Reels",
        "Stories",
        "Community management",
        "Paid ads",
    ],
    "required_skills": [],
    "clarifying_questions": [],
    "acceptance_criteria": [],
    "assumptions": [],
    "warnings": [],
}

BAKERY_NARROW_BRIEF = {
    "title": "Three Instagram posts for the new menu",
    "objective": "Deliver three ready-to-post Instagram images promoting the new seasonal menu.",
    "deliverables": ["Three ready-to-post images with captions"],
    "required_skills": ["Canva", "Copywriting"],
    "clarifying_questions": ["Do you have photos of the new menu items?"],
    "acceptance_criteria": ["Three images with captions are delivered"],
    "assumptions": ["The bakery already has an Instagram account"],
    "warnings": [],
    "exclusions": ["Paid advertising", "Ongoing account management"],
    "client_responsibilities": ["Provide photos of the new menu items"],
    "revision_expectations": ["One round of revisions"],
}

TUTOR_REQUEST = {
    "project_name": "Maths tutor",
    "description": "I need a simple one-page website for my tutoring.",
    "outcome": "Students can find my rates and contact me.",
    "budget": 3000,
    "deadline": "1 week",
}

TUTOR_BRIEF = {
    "title": "One-page tutoring website",
    "objective": "Build a single-page website with my subjects, rates, and a contact section.",
    "deliverables": ["One-page website with three sections"],
    "required_skills": ["HTML", "CSS"],
    "clarifying_questions": [],
    "acceptance_criteria": ["The page is published and loads in a browser"],
    "assumptions": ["The tutor will provide the text and rates"],
    "warnings": [],
    "exclusions": ["Domain purchase and hosting setup are not included"],
    "client_responsibilities": ["Provide the tutoring text, rates, and contact details"],
    "revision_expectations": ["Two rounds of revisions"],
}

SHOP_REQUEST = {
    "project_name": "Corner shop",
    "description": "Write descriptions for our new products.",
    "outcome": "More products are found and bought online.",
    "budget": 1500,
    "deadline": "4 days",
}

SHOP_BRIEF = {
    "title": "Product listing descriptions",
    "objective": "Write clear listing descriptions for ten new shop products.",
    "deliverables": ["Ten product descriptions (about 80 words each)"],
    "required_skills": ["Copywriting"],
    "clarifying_questions": ["Can you share the product details and prices?"],
    "acceptance_criteria": ["Ten descriptions are delivered and match the product list"],
    "assumptions": ["The shop will supply product details"],
    "warnings": [],
    "exclusions": ["Product photography is not included"],
    "client_responsibilities": ["Provide product details and prices"],
    "revision_expectations": ["One round of revisions"],
}


class BakeryExampleTests(unittest.TestCase):
    def test_overbroad_request_is_a_reason_to_review(self) -> None:
        signals = fairscope.scope_signals(BAKERY_REQUEST, BAKERY_BROAD_BRIEF)
        messages = " ".join(finding["message"].lower() for finding in signals)
        self.assertIn("broad", messages)

    def test_narrowed_version_raises_fewer_deterministic_warnings(self) -> None:
        broad = [f for f in fairscope.scope_signals(BAKERY_REQUEST, BAKERY_BROAD_BRIEF)
                 if f["level"] == "warning"]
        narrow = [f for f in fairscope.scope_signals(BAKERY_REQUEST, BAKERY_NARROW_BRIEF)
                  if f["level"] == "warning"]
        self.assertGreater(len(broad), len(narrow))

    def test_narrowed_version_defines_verifiable_outputs(self) -> None:
        checks = {c["key"]: c for c in fairscope.clarity_checks(BAKERY_REQUEST, BAKERY_NARROW_BRIEF)["checks"]}
        self.assertEqual(checks["deliverables"]["status"], fairscope.STATUS_OK)
        self.assertEqual(checks["acceptance_criteria"]["status"], fairscope.STATUS_OK)

    def test_budget_and_deadline_are_preserved(self) -> None:
        passport = fairscope.build_passport(BAKERY_NARROW_BRIEF, BAKERY_REQUEST)
        self.assertEqual(passport["sections"]["budget"]["value"], 800.0)
        self.assertEqual(passport["sections"]["deadline"]["value"], "2 days")

    def test_narrowed_passport_is_publishable(self) -> None:
        passport = fairscope.build_passport(BAKERY_NARROW_BRIEF, BAKERY_REQUEST)
        self.assertTrue(fairscope.passport_is_publishable(passport))


class TutorExampleTests(unittest.TestCase):
    def test_passport_preserves_budget_and_deadline(self) -> None:
        passport = fairscope.build_passport(TUTOR_BRIEF, TUTOR_REQUEST)
        self.assertEqual(passport["sections"]["budget"]["value"], 3000.0)
        self.assertEqual(passport["sections"]["deadline"]["value"], "1 week")

    def test_client_responsibilities_and_exclusions_are_kept(self) -> None:
        passport = fairscope.build_passport(TUTOR_BRIEF, TUTOR_REQUEST)
        sections = passport["sections"]
        self.assertIn("Domain purchase", " ".join(sections["exclusions"]["value"]))
        self.assertTrue(sections["client_responsibilities"]["value"])

    def test_if_the_owner_leaves_the_brief_empty_it_is_flagged_not_invented(self) -> None:
        passport = fairscope.build_passport({}, TUTOR_REQUEST)
        sections = passport["sections"]
        self.assertTrue(sections["objective"]["needs_clarification"])
        self.assertEqual(sections["objective"]["value"], "")
        self.assertEqual(sections["deliverables"]["value"], [])
        self.assertFalse(fairscope.passport_is_publishable(passport))


class ShopExampleTests(unittest.TestCase):
    def test_passport_preserves_budget_and_deadline(self) -> None:
        passport = fairscope.build_passport(SHOP_BRIEF, SHOP_REQUEST)
        self.assertEqual(passport["sections"]["budget"]["value"], 1500.0)
        self.assertEqual(passport["sections"]["deadline"]["value"], "4 days")

    def test_open_question_is_flagged_honestly(self) -> None:
        analysis = fairscope.analyze_brief(SHOP_REQUEST, SHOP_BRIEF)
        checks = {c["key"]: c for c in analysis["clarity"]["checks"]}
        self.assertEqual(checks["open_questions"]["status"], fairscope.STATUS_NEEDS)
        self.assertEqual(analysis["ai_suggestions"]["questions"], SHOP_BRIEF["clarifying_questions"])

    def test_passport_is_publishable(self) -> None:
        passport = fairscope.build_passport(SHOP_BRIEF, SHOP_REQUEST)
        self.assertTrue(fairscope.passport_is_publishable(passport))


class NoFeasibilityGuaranteeTests(unittest.TestCase):
    def test_next_action_has_no_numeric_score_or_percentage(self) -> None:
        for request, brief in (
            (BAKERY_REQUEST, BAKERY_BROAD_BRIEF),
            (TUTOR_REQUEST, TUTOR_BRIEF),
            (SHOP_REQUEST, SHOP_BRIEF),
        ):
            action = fairscope.analyze_brief(request, brief)["next_action"]
            joined = " ".join(action["steps"]) + " " + action["summary"]
            self.assertNotIn("%", joined)

    def test_no_signal_claims_a_budget_is_fair_or_unfair(self) -> None:
        for request, brief in (
            (BAKERY_REQUEST, BAKERY_BROAD_BRIEF),
            (TUTOR_REQUEST, TUTOR_BRIEF),
            (SHOP_REQUEST, SHOP_BRIEF),
        ):
            for finding in fairscope.scope_signals(request, brief):
                self.assertNotIn("fair", finding["message"].lower())


if __name__ == "__main__":
    unittest.main()
