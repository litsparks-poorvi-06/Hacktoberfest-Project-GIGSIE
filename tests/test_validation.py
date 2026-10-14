"""Tests for validation.py - task/profile validation and skill matching.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import validation as v  # noqa: E402


COMPLETE_GIG = {
    "id": "g1",
    "title": "Promote a new menu on Instagram",
    "business_name": "Sunrise Bakery",
    "work_needed": "Help promote the new seasonal menu on Instagram.",
    "desired_outcome": "More local customers visit the shop.",
    "budget_inr": 800,
    "deadline": "5 days",
    "brief": {
        "project_objective": "Promote the new menu.",
        "proposed_deliverables": ["Three Instagram posts with captions"],
        "required_skills": ["Canva", "Copywriting", "Social media marketing"],
        "acceptance_criteria": ["Posts are ready to publish"],
    },
    "sample": True,
}

COMPLETE_PROFILE = {
    "display_name": "Sam",
    "skills": ["Canva", "Copywriting"],
    "experience_level": "Beginner",
    "bio": "Student learning design.",
    "available_time": "10 days",
    "portfolio_links": ["https://example.com/portfolio"],
}


class TaskValidationTests(unittest.TestCase):
    def test_complete_gig_passes(self) -> None:
        self.assertFalse(v.has_errors(v.validate_task(COMPLETE_GIG)))

    def test_missing_description_is_error(self) -> None:
        gig = dict(COMPLETE_GIG)
        gig["work_needed"] = ""
        findings = v.validate_task(gig)
        self.assertTrue(v.has_errors(findings))
        self.assertTrue(any("work" in f["message"].lower() for f in findings))

    def test_missing_outcome_is_error(self) -> None:
        gig = dict(COMPLETE_GIG)
        gig["desired_outcome"] = ""
        self.assertTrue(v.has_errors(v.validate_task(gig)))

    def test_missing_deliverables_is_error(self) -> None:
        gig = {
            "title": "A gig",
            "work_needed": "Do work",
            "desired_outcome": "Get results",
            "brief": {"proposed_deliverables": []},
        }
        findings = v.validate_task(gig)
        self.assertTrue(v.has_errors(findings))
        self.assertTrue(any("deliverable" in f["message"].lower() for f in findings))

    def test_budget_and_deadline_optional(self) -> None:
        gig = {
            "title": "A gig",
            "work_needed": "Do work",
            "desired_outcome": "Get results",
            "brief": {"proposed_deliverables": ["Something"]},
        }
        self.assertFalse(v.has_errors(v.validate_task(gig)))

    def test_negative_budget_is_error(self) -> None:
        gig = dict(COMPLETE_GIG)
        gig["budget_inr"] = -100
        self.assertTrue(v.has_errors(v.validate_task(gig)))

    def test_non_numeric_budget_is_error(self) -> None:
        gig = dict(COMPLETE_GIG)
        gig["budget_inr"] = "lots"
        self.assertTrue(v.has_errors(v.validate_task(gig)))

    def test_title_missing_is_warning_not_error(self) -> None:
        gig = dict(COMPLETE_GIG)
        gig["title"] = ""
        gig["project_objective"] = ""
        findings = v.validate_task(gig)
        self.assertFalse(v.has_errors(findings))
        self.assertTrue(any(f["level"] == "warning" for f in findings))

    def test_wrong_types_do_not_crash(self) -> None:
        for bad in (None, "text", 42, [], {"brief": "not a dict"}, {"required_skills": 99}):
            findings = v.validate_task(bad)
            self.assertIsInstance(findings, list)

    def test_reads_alternative_field_names(self) -> None:
        # The business-form shape uses description/outcome/budget instead.
        gig = {
            "title": "T",
            "description": "Do work",
            "outcome": "Get results",
            "budget": 500,
            "proposed_deliverables": ["Something"],
        }
        self.assertFalse(v.has_errors(v.validate_task(gig)))


class ProfileValidationTests(unittest.TestCase):
    def test_complete_profile_passes(self) -> None:
        self.assertFalse(v.has_errors(v.validate_profile(COMPLETE_PROFILE)))

    def test_empty_profile_has_errors(self) -> None:
        findings = v.validate_profile({})
        self.assertTrue(v.has_errors(findings))
        self.assertEqual(len([f for f in findings if f["level"] == "error"]), 2)

    def test_beginner_without_portfolio_is_ok(self) -> None:
        profile = {"display_name": "Newbie", "skills": ["Canva"]}
        self.assertFalse(v.has_errors(v.validate_profile(profile)))

    def test_invalid_experience_level_is_warning_not_error(self) -> None:
        profile = dict(COMPLETE_PROFILE)
        profile["experience_level"] = "Expert-ish"
        findings = v.validate_profile(profile)
        self.assertFalse(v.has_errors(findings))
        self.assertTrue(any("experience level" in f["message"].lower() for f in findings))

    def test_bad_portfolio_link_is_warning(self) -> None:
        profile = dict(COMPLETE_PROFILE)
        profile["portfolio_links"] = ["not a link"]
        findings = v.validate_profile(profile)
        self.assertFalse(v.has_errors(findings))
        self.assertTrue(any("portfolio link" in f["message"].lower() for f in findings))

    def test_wrong_types_do_not_crash(self) -> None:
        for bad in (None, "text", 3, []):
            self.assertIsInstance(v.validate_profile(bad), list)


class MatchingTests(unittest.TestCase):
    def _profile(self, skills, available_time="10 days"):
        return {"display_name": "Sam", "skills": skills, "available_time": available_time}

    def test_case_insensitive_match(self) -> None:
        result = v.match_gig_to_skills(COMPLETE_GIG, self._profile(["canva"]))
        self.assertIn("Canva", result["matched"])
        self.assertEqual(result["score"], 33)  # 1 of 3 required skills

    def test_full_match_scores_100(self) -> None:
        result = v.match_gig_to_skills(
            COMPLETE_GIG, self._profile(["Canva", "Copywriting", "Social media marketing"])
        )
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["missing"], [])

    def test_duplicate_skills_do_not_inflate(self) -> None:
        single = v.match_gig_to_skills(COMPLETE_GIG, self._profile(["Canva"]))
        duplicated = v.match_gig_to_skills(COMPLETE_GIG, self._profile(["Canva", "canva", "CANVA"]))
        self.assertEqual(single["score"], duplicated["score"])

    def test_duplicate_skills_in_gig_do_not_inflate(self) -> None:
        gig = dict(COMPLETE_GIG)
        gig["brief"] = dict(COMPLETE_GIG["brief"])
        gig["brief"]["required_skills"] = ["Canva", "canva"]
        result = v.match_gig_to_skills(gig, self._profile(["Canva"]))
        self.assertEqual(result["score"], 100)

    def test_matched_and_missing_reported(self) -> None:
        result = v.match_gig_to_skills(
            COMPLETE_GIG, self._profile(["Canva", "Copywriting", "Social media marketing", "Graphic design"])
        )
        self.assertEqual(len(result["matched"]), 3)
        self.assertEqual(result["missing"], [])

    def test_partial_match(self) -> None:
        gig = dict(COMPLETE_GIG)
        gig["brief"] = dict(COMPLETE_GIG["brief"])
        gig["brief"]["required_skills"] = ["Canva", "Copywriting", "Graphic design", "Video editing"]
        result = v.match_gig_to_skills(gig, self._profile(["Canva", "Copywriting"]))
        self.assertEqual(result["score"], 50)
        self.assertEqual(sorted(result["missing"]), ["Graphic design", "Video editing"])

    def test_missing_required_skill_is_not_full_match(self) -> None:
        result = v.match_gig_to_skills(COMPLETE_GIG, self._profile(["Canva"]))
        self.assertLess(result["score"], 100)
        self.assertTrue(result["missing"])

    def test_no_required_skills_gives_no_score(self) -> None:
        gig = {"title": "T", "work_needed": "w", "desired_outcome": "o", "brief": {"proposed_deliverables": ["d"]}}
        result = v.match_gig_to_skills(gig, self._profile(["Canva"]))
        self.assertIsNone(result["score"])

    def test_no_profile_skills_gives_no_score(self) -> None:
        result = v.match_gig_to_skills(COMPLETE_GIG, self._profile([]))
        self.assertIsNone(result["score"])
        self.assertIn("does not list any skills", " ".join(result["reasons"]))

    def test_phrase_match(self) -> None:
        gig = dict(COMPLETE_GIG)
        gig["brief"] = dict(COMPLETE_GIG["brief"])
        gig["brief"]["required_skills"] = ["Graphic design"]
        result = v.match_gig_to_skills(gig, self._profile(["Graphic design tools"]))
        self.assertIn("Graphic design", result["matched"])

    def test_single_generic_word_is_not_a_match(self) -> None:
        gig = dict(COMPLETE_GIG)
        gig["brief"] = dict(COMPLETE_GIG["brief"])
        gig["brief"]["required_skills"] = ["Design"]
        result = v.match_gig_to_skills(gig, self._profile(["Graphic design"]))
        self.assertEqual(result["matched"], [])
        self.assertEqual(result["missing"], ["Design"])

    def test_availability_mismatch_reported(self) -> None:
        gig = dict(COMPLETE_GIG)
        gig["deadline"] = "10 days"
        result = v.match_gig_to_skills(gig, self._profile(["Canva"], available_time="2 days"))
        self.assertIn("shorter than", result["availability_note"])

    def test_availability_not_comparable_when_only_hours(self) -> None:
        result = v.match_gig_to_skills(COMPLETE_GIG, self._profile(["Canva"], available_time="10 hrs/week"))
        self.assertIn("could not be checked", result["availability_note"])

    def test_disclaimer_present(self) -> None:
        result = v.match_gig_to_skills(COMPLETE_GIG, self._profile(["Canva"]))
        self.assertIn("self-reported", result["disclaimer"])

    def test_never_raises_on_bad_types(self) -> None:
        result = v.match_gig_to_skills(None, None)
        self.assertIsNone(result["score"])
        self.assertEqual(result["missing"], [])

    def test_rank_gigs_sorts_best_first_and_puts_none_last(self) -> None:
        strong = dict(COMPLETE_GIG)
        strong["id"] = "strong"
        weak = dict(COMPLETE_GIG)
        weak["id"] = "weak"
        weak["brief"] = dict(COMPLETE_GIG["brief"])
        weak["brief"]["required_skills"] = ["Canva", "Photography", "Video editing", "SEO"]
        no_skills = {
            "id": "none",
            "title": "T",
            "work_needed": "w",
            "desired_outcome": "o",
            "brief": {"proposed_deliverables": ["d"]},
        }
        ranked = v.rank_gigs([weak, no_skills, strong], self._profile(["Canva", "Copywriting"]))
        self.assertEqual(ranked[0]["gig"]["id"], "strong")
        self.assertEqual(ranked[-1]["gig"]["id"], "none")


if __name__ == "__main__":
    unittest.main()
