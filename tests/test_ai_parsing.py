"""Tests for gigsie_ai.py - JSON parsing and application generation helpers.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gigsie_ai as ai  # noqa: E402


class AIParsingTests(unittest.TestCase):
    def test_parse_application_basic(self) -> None:
        raw = (
            '{"opening": "Hi, I am interested in your gig.", '
            '"why_good_fit": ["I have Canva experience."], '
            '"proposed_approach": ["Create three posts."], '
            '"questions_for_business": ["Do you have images?"], '
            '"availability_note": "I am free for 2 days."}'
        )
        draft, problems = ai.parse_application(raw)
        self.assertEqual(draft["opening"], "Hi, I am interested in your gig.")
        self.assertEqual(draft["why_good_fit"], ["I have Canva experience."])
        self.assertEqual(draft["proposed_approach"], ["Create three posts."])
        self.assertEqual(draft["questions_for_business"], ["Do you have images?"])
        self.assertEqual(draft["availability_note"], "I am free for 2 days.")
        self.assertEqual(problems, [])

    def test_parse_application_fenced(self) -> None:
        raw = "```json\n" + (
            '{"opening": "Hi.", '
            '"why_good_fit": ["Skill"], '
            '"proposed_approach": ["Step 1"], '
            '"questions_for_business": [], '
            '"availability_note": "Free"}'
        ) + "\n```"
        draft, problems = ai.parse_application(raw)
        self.assertEqual(draft["opening"], "Hi.")
        self.assertEqual(draft["why_good_fit"], ["Skill"])
        self.assertEqual(draft["questions_for_business"], [])
        self.assertEqual(problems, [])

    def test_parse_application_prose_wrapped(self) -> None:
        raw = "Sure! Here is a draft:\n" + (
            '{"opening": "Hi.", '
            '"why_good_fit": ["Canva"], '
            '"proposed_approach": ["Plan"], '
            '"questions_for_business": ["Any colors?"], '
            '"availability_note": "Available this week"}'
        ) + "\nLet me know if you want changes."
        draft, _ = ai.parse_application(raw)
        self.assertEqual(draft["why_good_fit"], ["Canva"])

    def test_parse_application_malformed_raises(self) -> None:
        with self.assertRaises(ai.GigsieAIError):
            ai.parse_application('{"opening": "x", ')

    def test_parse_application_empty_raises(self) -> None:
        with self.assertRaises(ai.GigsieAIError):
            ai.parse_application("   ")

    def test_parse_application_missing_fields_normalized(self) -> None:
        raw = '{"opening": "Hi."}'
        draft, problems = ai.parse_application(raw)
        self.assertEqual(draft["why_good_fit"], [])
        self.assertEqual(draft["proposed_approach"], [])
        self.assertEqual(draft["questions_for_business"], [])
        self.assertEqual(draft["availability_note"], "")
        self.assertGreater(len(problems), 0)

    def test_parse_application_string_coerced(self) -> None:
        raw = (
            '{"opening": "Hi.", '
            '"why_good_fit": "Single reason", '
            '"proposed_approach": [], '
            '"questions_for_business": [], '
            '"availability_note": "Free"}'
        )
        draft, _ = ai.parse_application(raw)
        self.assertEqual(draft["why_good_fit"], ["Single reason"])

    def test_build_application_prompt_contains_gig_and_profile(self) -> None:
        gig = {
            "title": "Promote bakery menu",
            "work_needed": "Instagram posts",
            "desired_outcome": "More visitors",
            "deadline": "2 days",
            "budget_inr": 800,
            "required_skills": ["Canva"],
        }
        profile = {
            "display_name": "Sam",
            "skills": ["Canva", "Copywriting"],
            "experience_level": "Beginner",
            "bio": "Student",
            "available_time": "10 days",
            "portfolio_links": ["https://example.com"],
        }
        prompt = ai.build_application_user_prompt(gig, profile)
        self.assertIn("Promote bakery menu", prompt)
        self.assertIn("Instagram posts", prompt)
        self.assertIn("Sam", prompt)
        self.assertIn("Canva, Copywriting", prompt)

    def test_parse_brief_uses_new_schema(self) -> None:
        raw = (
            '{"title": "Promote the new menu",'
            ' "objective": "Promote the new seasonal menu on Instagram",'
            ' "deliverables": ["Menu poster"],'
            ' "required_skills": ["Canva"],'
            ' "clarifying_questions": ["Who is the audience?"],'
            ' "acceptance_criteria": ["Poster is print-ready"],'
            ' "assumptions": ["Local customers only"],'
            ' "warnings": ["Two days is tight"]}'
        )
        brief, problems = ai.parse_brief(raw)
        self.assertEqual(brief["title"], "Promote the new menu")
        self.assertEqual(brief["objective"], "Promote the new seasonal menu on Instagram")
        self.assertEqual(brief["deliverables"], ["Menu poster"])
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
