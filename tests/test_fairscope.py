"""Unit tests for fairscope.py - deterministic scope review + Gig Passport.

Everything here is plain Python: no AI, no network, no Streamlit. The model's
language is not tested here (see test_fairscope_ai.py); these tests only cover
the deterministic checks FairScope adds on top, and the Gig Passport.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fairscope  # noqa: E402


COMPLETE_REQUEST = {
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
}


def _clarity(brief, request=None):
    return fairscope.clarity_checks(request or COMPLETE_REQUEST, brief)


def _status(brief, key, request=None):
    for check in _clarity(brief, request)["checks"]:
        if check["key"] == key:
            return check["status"]
    raise AssertionError(f"no clarity check named {key!r}")


class ClarityCheckTests(unittest.TestCase):
    def test_complete_brief_passes_every_check(self) -> None:
        checks = _clarity(COMPLETE_BRIEF)["checks"]
        self.assertTrue(checks)
        for check in checks:
            self.assertEqual(check["status"], fairscope.STATUS_OK, check["label"])

    def test_missing_objective_is_missing_and_essential(self) -> None:
        brief = dict(COMPLETE_BRIEF, objective="")
        check = next(c for c in _clarity(brief)["checks"] if c["key"] == "objective")
        self.assertEqual(check["status"], fairscope.STATUS_MISSING)
        self.assertTrue(check["essential"])

    def test_vague_objective_needs_clarification(self) -> None:
        self.assertEqual(
            _status(dict(COMPLETE_BRIEF, objective="Make it nice"), "objective"),
            fairscope.STATUS_NEEDS,
        )

    def test_no_deliverables_is_missing(self) -> None:
        self.assertEqual(
            _status(dict(COMPLETE_BRIEF, deliverables=[]), "deliverables"),
            fairscope.STATUS_MISSING,
        )

    def test_vague_deliverable_needs_clarification(self) -> None:
        self.assertEqual(
            _status(dict(COMPLETE_BRIEF, deliverables=["Some nice posts"]), "deliverables"),
            fairscope.STATUS_NEEDS,
        )

    def test_no_acceptance_criteria_is_missing(self) -> None:
        self.assertEqual(
            _status(dict(COMPLETE_BRIEF, acceptance_criteria=[]), "acceptance_criteria"),
            fairscope.STATUS_MISSING,
        )

    def test_uncheckable_acceptance_criteria_needs_clarification(self) -> None:
        self.assertEqual(
            _status(dict(COMPLETE_BRIEF, acceptance_criteria=["Looks nice"]), "acceptance_criteria"),
            fairscope.STATUS_NEEDS,
        )

    def test_no_skills_needs_clarification(self) -> None:
        self.assertEqual(
            _status(dict(COMPLETE_BRIEF, required_skills=[]), "required_skills"),
            fairscope.STATUS_NEEDS,
        )

    def test_missing_scope_boundary_needs_clarification(self) -> None:
        brief = dict(COMPLETE_BRIEF, exclusions=[])
        self.assertEqual(_status(brief, "scope_boundaries"), fairscope.STATUS_NEEDS)

    def test_open_questions_are_flagged(self) -> None:
        brief = dict(COMPLETE_BRIEF, clarifying_questions=["Do you have photos?"])
        self.assertEqual(_status(brief, "open_questions"), fairscope.STATUS_NEEDS)

    def test_never_raises_on_bad_types(self) -> None:
        for bad in (None, "text", 5, [], {"deliverables": 99}):
            self.assertIsInstance(fairscope.clarity_checks(bad, bad), dict)


class ScopeSignalTests(unittest.TestCase):
    def _signals(self, request=None, brief=None):
        return fairscope.scope_signals(request or COMPLETE_REQUEST, brief or COMPLETE_BRIEF)

    def test_all_signals_are_deterministic(self) -> None:
        for finding in self._signals():
            self.assertEqual(finding["source"], "deterministic")

    def test_broad_request_is_flagged(self) -> None:
        request = dict(COMPLETE_REQUEST, description="Manage all our marketing.")
        brief = dict(COMPLETE_BRIEF, exclusions=[])
        messages = " ".join(
            f["message"].lower()
            for f in self._signals(request=request, brief=brief)
        )
        self.assertIn("broad", messages)

    def test_broad_request_with_clear_boundaries_is_not_flagged(self) -> None:
        request = dict(COMPLETE_REQUEST, description="Manage all our marketing.")
        # COMPLETE_BRIEF carries an explicit exclusion, so the boundary is clear.
        messages = " ".join(
            f["message"].lower() for f in self._signals(request=request, brief=COMPLETE_BRIEF)
        )
        self.assertNotIn("broad", messages)

    def test_many_deliverables_with_a_long_deadline_is_flagged(self) -> None:
        brief = dict(COMPLETE_BRIEF, deliverables=[f"Deliverable {i}" for i in range(1, 6)])
        messages = " ".join(f["message"].lower() for f in self._signals(brief=brief))
        self.assertIn("deliverables are listed", messages)

    def test_many_deliverables_with_a_short_deadline_is_flagged(self) -> None:
        request = dict(COMPLETE_REQUEST, deadline="2 days")
        brief = dict(COMPLETE_BRIEF, deliverables=[f"Deliverable {i}" for i in range(1, 6)])
        findings = self._signals(request=request, brief=brief)
        messages = " ".join(f["message"].lower() for f in findings)
        self.assertIn("deliverable", messages)

    def test_missing_assets_are_flagged(self) -> None:
        request = dict(COMPLETE_REQUEST, description="Edit our product photos.")
        messages = " ".join(f["message"].lower() for f in self._signals(request=request))
        self.assertIn("assets", messages)

    def test_revision_mention_without_a_limit_is_flagged(self) -> None:
        request = dict(COMPLETE_REQUEST, description="Design the banner and handle revisions.")
        levels = {f["level"] for f in self._signals(request=request)}
        messages = " ".join(f["message"].lower() for f in self._signals(request=request))
        self.assertIn("revision", messages)
        self.assertIn("info", levels)

    def test_uncheckable_acceptance_criteria_are_flagged(self) -> None:
        brief = dict(COMPLETE_BRIEF, acceptance_criteria=["Make it look nice"])
        messages = " ".join(f["message"].lower() for f in self._signals(brief=brief))
        self.assertIn("cannot be checked objectively", messages)

    def test_no_budget_or_price_judgement_is_made(self) -> None:
        for finding in self._signals():
            self.assertIsNone(
                re.search(r"\b(fair|price|pricing|market rate|worth|overpriced)\b",
                          finding["message"], re.IGNORECASE),
                finding["message"],
            )

    def test_never_raises_on_bad_types(self) -> None:
        self.assertIsInstance(fairscope.scope_signals(None, None), list)


class RecommendedActionTests(unittest.TestCase):
    def test_missing_essentials_are_prioritised(self) -> None:
        brief = dict(COMPLETE_BRIEF, objective="", acceptance_criteria=[])
        analysis = fairscope.analyze_brief(COMPLETE_REQUEST, brief)
        action = analysis["next_action"]
        self.assertIn("essential", action["summary"].lower())
        self.assertTrue(action["steps"])

    def test_complete_brief_is_reviewable(self) -> None:
        analysis = fairscope.analyze_brief(COMPLETE_REQUEST, COMPLETE_BRIEF)
        self.assertIn("reviewable", analysis["next_action"]["summary"].lower())

    def test_no_numeric_feasibility_score_is_offered(self) -> None:
        analysis = fairscope.analyze_brief(COMPLETE_REQUEST, COMPLETE_BRIEF)
        joined = " ".join(analysis["next_action"]["steps"])
        self.assertNotIn("%", joined)

    def test_ai_suggestions_are_kept_separate_from_deterministic_findings(self) -> None:
        brief = dict(COMPLETE_BRIEF, warnings=["A model warning"], clarifying_questions=["A model question"])
        analysis = fairscope.analyze_brief(COMPLETE_REQUEST, brief)
        self.assertEqual(analysis["ai_suggestions"]["warnings"], ["A model warning"])
        self.assertEqual(analysis["ai_suggestions"]["questions"], ["A model question"])
        for finding in analysis["signals"]:
            self.assertEqual(finding["source"], "deterministic")


class PassportBuildTests(unittest.TestCase):
    def test_sections_are_complete(self) -> None:
        passport = fairscope.build_passport(COMPLETE_BRIEF, COMPLETE_REQUEST)
        keys = set(passport["sections"])
        for expected in (
            "objective",
            "deliverables",
            "definition_of_done",
            "included_work",
            "exclusions",
            "required_skills",
            "client_responsibilities",
            "revision_expectations",
            "open_questions",
            "assumptions",
            "budget",
            "deadline",
            "scope_warnings",
        ):
            self.assertIn(expected, keys)

    def test_values_are_copied_from_the_brief_and_request(self) -> None:
        passport = fairscope.build_passport(COMPLETE_BRIEF, COMPLETE_REQUEST)
        sections = passport["sections"]
        self.assertEqual(sections["objective"]["value"], COMPLETE_BRIEF["objective"])
        self.assertEqual(sections["deliverables"]["value"], COMPLETE_BRIEF["deliverables"])
        self.assertEqual(sections["definition_of_done"]["value"], COMPLETE_BRIEF["acceptance_criteria"])
        self.assertEqual(sections["budget"]["value"], 800.0)
        self.assertEqual(sections["deadline"]["value"], "5 days")

    def test_missing_acceptance_criteria_needs_clarification(self) -> None:
        passport = fairscope.build_passport(dict(COMPLETE_BRIEF, acceptance_criteria=[]), COMPLETE_REQUEST)
        self.assertTrue(passport["sections"]["definition_of_done"]["needs_clarification"])

    def test_optional_empty_sections_are_not_marked_as_needing_clarification(self) -> None:
        passport = fairscope.build_passport(COMPLETE_BRIEF, COMPLETE_REQUEST)
        sections = passport["sections"]
        for key in ("exclusions", "client_responsibilities", "revision_expectations",
                    "open_questions", "assumptions", "scope_warnings"):
            self.assertFalse(sections[key]["needs_clarification"], key)

    def test_missing_information_is_never_invented(self) -> None:
        passport = fairscope.build_passport({}, {})
        sections = passport["sections"]
        self.assertEqual(sections["exclusions"]["value"], [])
        self.assertEqual(sections["client_responsibilities"]["value"], [])
        self.assertEqual(sections["revision_expectations"]["value"], [])
        self.assertTrue(sections["objective"]["needs_clarification"])

    def test_scope_warnings_combine_model_and_signal_messages(self) -> None:
        brief = dict(COMPLETE_BRIEF, warnings=["Model warning"], exclusions=[])
        request = dict(COMPLETE_REQUEST, description="Manage all our marketing.")
        passport = fairscope.build_passport(brief, request)
        warnings = passport["sections"]["scope_warnings"]["value"]
        self.assertIn("Model warning", warnings)
        self.assertTrue(any("broad" in message.lower() for message in warnings))

    def test_update_values_resolves_clarification(self) -> None:
        passport = fairscope.build_passport(dict(COMPLETE_BRIEF, acceptance_criteria=[]), COMPLETE_REQUEST)
        self.assertTrue(passport["sections"]["definition_of_done"]["needs_clarification"])
        updated = fairscope.update_passport_values(
            passport, {"definition_of_done": ["Three posts delivered"]}
        )
        self.assertFalse(updated["sections"]["definition_of_done"]["needs_clarification"])
        # The original is untouched (no mutation).
        self.assertTrue(passport["sections"]["definition_of_done"]["needs_clarification"])

    def test_acknowledge_clears_essential_issues(self) -> None:
        passport = fairscope.build_passport(dict(COMPLETE_BRIEF, acceptance_criteria=[]), COMPLETE_REQUEST)
        self.assertFalse(fairscope.passport_is_publishable(passport))
        self.assertIn("definition_of_done", fairscope.passport_essential_issues(passport))
        acknowledged = fairscope.acknowledge(passport, ["definition_of_done"])
        self.assertTrue(fairscope.passport_is_publishable(acknowledged))

    def test_essential_gap_blocks_until_resolved_or_acknowledged(self) -> None:
        passport = fairscope.build_passport(dict(COMPLETE_BRIEF, required_skills=[]), COMPLETE_REQUEST)
        self.assertEqual(fairscope.passport_essential_issues(passport), ["required_skills"])
        self.assertIn("Required skills", fairscope.passport_issue_labels(passport))

    def test_complete_passport_is_publishable(self) -> None:
        passport = fairscope.build_passport(COMPLETE_BRIEF, COMPLETE_REQUEST)
        self.assertTrue(fairscope.passport_is_publishable(passport))

    def test_budget_and_deadline_are_preserved_verbatim(self) -> None:
        request = dict(COMPLETE_REQUEST, budget=1234.5, deadline="3 weeks")
        passport = fairscope.build_passport(COMPLETE_BRIEF, request)
        self.assertEqual(passport["sections"]["budget"]["value"], 1234.5)
        self.assertEqual(passport["sections"]["deadline"]["value"], "3 weeks")


class PassportForGigTests(unittest.TestCase):
    def test_stored_passport_is_returned(self) -> None:
        passport = fairscope.build_passport(COMPLETE_BRIEF, COMPLETE_REQUEST)
        gig = {"id": "g1", "passport": passport}
        self.assertIs(fairscope.passport_for_gig(gig), passport)

    def test_legacy_gig_gets_a_derived_passport(self) -> None:
        # The older sample schema uses project_objective / proposed_deliverables.
        gig = {
            "id": "g_old",
            "title": "Old gig",
            "work_needed": "Promote the menu.",
            "desired_outcome": "More customers.",
            "budget_inr": 500,
            "deadline": "2 days",
            "brief": {
                "project_objective": "Promote the new menu.",
                "proposed_deliverables": ["Two Instagram posts"],
                "required_skills": ["Canva"],
                "acceptance_criteria": ["Two posts delivered"],
            },
        }
        passport = fairscope.passport_for_gig(gig)
        sections = passport["sections"]
        self.assertEqual(sections["objective"]["value"], "Promote the new menu.")
        self.assertEqual(sections["deliverables"]["value"], ["Two Instagram posts"])
        self.assertEqual(sections["budget"]["value"], 500.0)

    def test_bad_input_does_not_raise(self) -> None:
        self.assertIn("sections", fairscope.passport_for_gig(None))


class StrategyMetadataTests(unittest.TestCase):
    def test_three_strategies_are_defined(self) -> None:
        self.assertEqual(
            fairscope.SCOPE_STRATEGY_KEYS,
            ["budget_first", "outcome_first", "milestone_first"],
        )

    def test_labels_are_human_readable(self) -> None:
        self.assertEqual(fairscope.strategy_label("budget_first"), "Budget-first")
        self.assertEqual(fairscope.strategy_label("outcome_first"), "Outcome-first")
        self.assertEqual(fairscope.strategy_label("milestone_first"), "Milestone-first")

    def test_unknown_strategy_has_no_metadata(self) -> None:
        self.assertIsNone(fairscope.strategy_meta("nope"))
        self.assertEqual(fairscope.strategy_label("nope"), "nope")


if __name__ == "__main__":
    unittest.main()
