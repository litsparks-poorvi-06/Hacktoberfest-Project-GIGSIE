"""Tests for the FairScope scope-strategy support in gigsie_ai.py.

These tests NEVER call the real Groq API. A fake client stands in, so the suite
is fast, offline, and deterministic. They also prove the legacy behaviour is
unchanged when no strategy is requested.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fairscope  # noqa: E402
import gigsie_ai as ai  # noqa: E402


VALID_REQUEST = {
    "project_name": "Sunrise Bakery",
    "description": "Promote our new seasonal menu on Instagram.",
    "outcome": "More local customers visit the shop.",
    "budget": 800,
    "deadline": "2 days",
    "extra_context": "Most customers are nearby families.",
}

GOOD_BRIEF = {
    "title": "Instagram posts for a bakery menu",
    "objective": "Promote the new seasonal menu to local families on Instagram.",
    "deliverables": ["Three ready-to-post images with captions"],
    "required_skills": ["Canva", "Copywriting"],
    "clarifying_questions": ["Do you have photos of the menu items?"],
    "acceptance_criteria": ["Three images with captions are delivered"],
    "assumptions": ["The bakery already has an Instagram account"],
    "warnings": ["Two days is a short window if photos still need to be taken"],
}

NARROWED_BRIEF = dict(
    GOOD_BRIEF,
    deliverables=["Three ready-to-post images with captions"],
    exclusions=["Paid advertising", "Ongoing account management"],
    client_responsibilities=["Provide photos of the menu items"],
    revision_expectations=["One round of revisions"],
)


# ---------------------------------------------------------------------------
# Fake Groq objects (no network, no credentials)
# ---------------------------------------------------------------------------
class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content=None, choices=None):
        if choices is not None:
            self.choices = choices
        else:
            self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, completions):
        self.chat = _FakeChat(completions)


def _client_returning(text):
    completions = _FakeCompletions(response=_FakeResponse(content=text))
    return _FakeClient(completions), completions


class LegacyBehaviourTests(unittest.TestCase):
    def test_no_strategy_keeps_the_original_shape(self) -> None:
        client, _ = _client_returning(json.dumps(GOOD_BRIEF))
        with mock.patch.object(ai, "get_client", return_value=client):
            result = ai.generate_task_brief(dict(VALID_REQUEST))
        self.assertNotIn("scope_strategy", result)
        self.assertEqual(set(result["brief"]), {key for key, _ in ai.BRIEF_FIELDS})

    def test_no_strategy_uses_the_original_system_prompt(self) -> None:
        client, completions = _client_returning(json.dumps(GOOD_BRIEF))
        with mock.patch.object(ai, "get_client", return_value=client):
            ai.generate_task_brief(dict(VALID_REQUEST))
        self.assertEqual(completions.calls[0]["messages"][0]["content"], ai.SYSTEM_PROMPT)
        self.assertNotIn("CURRENT DRAFT", completions.calls[0]["messages"][1]["content"])

    def test_strategy_instructions_are_not_in_the_default_prompt(self) -> None:
        for key in fairscope.SCOPE_STRATEGY_KEYS:
            self.assertNotIn("Chosen strategy", ai.SYSTEM_PROMPT)


class StrategyGenerationTests(unittest.TestCase):
    def _generate(self, strategy, brief=None):
        client, completions = _client_returning(json.dumps(NARROWED_BRIEF))
        with mock.patch.object(ai, "get_client", return_value=client):
            result = ai.generate_task_brief(
                dict(VALID_REQUEST), scope_strategy=strategy, current_brief=brief or GOOD_BRIEF
            )
        return result, completions

    def test_every_strategy_is_accepted(self) -> None:
        for key in fairscope.SCOPE_STRATEGY_KEYS:
            result, _ = self._generate(key)
            self.assertEqual(result["scope_strategy"], key)

    def test_strategy_changes_the_system_prompt(self) -> None:
        _, completions = self._generate("budget_first")
        system = completions.calls[0]["messages"][0]["content"]
        self.assertIn("BUDGET-FIRST", system)

    def test_strategy_includes_the_current_draft_in_the_prompt(self) -> None:
        _, completions = self._generate("milestone_first")
        user = completions.calls[0]["messages"][1]["content"]
        self.assertIn("CURRENT DRAFT", user)
        self.assertIn(GOOD_BRIEF["objective"], user)

    def test_strategy_prompt_preserves_budget_and_deadline(self) -> None:
        _, completions = self._generate("outcome_first")
        user = completions.calls[0]["messages"][1]["content"]
        self.assertIn("800", user)
        self.assertIn("2 days", user)

    def test_strategy_prompt_forbids_silent_budget_changes(self) -> None:
        _, completions = self._generate("outcome_first")
        system = completions.calls[0]["messages"][0]["content"].lower()
        self.assertIn("do not", system)
        self.assertIn("budget", system)

    def test_only_one_api_call_is_made_per_strategy(self) -> None:
        _, completions = self._generate("budget_first")
        self.assertEqual(len(completions.calls), 1)

    def test_optional_passport_keys_are_preserved(self) -> None:
        result, _ = self._generate("budget_first")
        brief = result["brief"]
        self.assertEqual(brief["exclusions"], NARROWED_BRIEF["exclusions"])
        self.assertEqual(brief["client_responsibilities"], NARROWED_BRIEF["client_responsibilities"])
        self.assertEqual(brief["revision_expectations"], NARROWED_BRIEF["revision_expectations"])

    def test_legacy_reply_without_optional_keys_has_none(self) -> None:
        client, _ = _client_returning(json.dumps(GOOD_BRIEF))
        with mock.patch.object(ai, "get_client", return_value=client):
            result = ai.generate_task_brief(
                dict(VALID_REQUEST), scope_strategy="budget_first", current_brief=GOOD_BRIEF
            )
        for key in ai.OPTIONAL_BRIEF_LIST_FIELDS:
            self.assertNotIn(key, result["brief"])

    def test_strategy_wrapper_delegates(self) -> None:
        client, _ = _client_returning(json.dumps(NARROWED_BRIEF))
        with mock.patch.object(ai, "get_client", return_value=client):
            result = ai.generate_scope_variant(dict(VALID_REQUEST), GOOD_BRIEF, "milestone_first")
        self.assertEqual(result["scope_strategy"], "milestone_first")


class StrategyErrorTests(unittest.TestCase):
    def test_unknown_strategy_is_rejected_without_an_api_call(self) -> None:
        with mock.patch.object(ai, "_call_model") as fake_call:
            with self.assertRaises(ai.GigsieAIError):
                ai.generate_task_brief(dict(VALID_REQUEST), scope_strategy="cheapest")
            fake_call.assert_not_called()

    def test_strategy_failure_raises_and_returns_no_brief(self) -> None:
        client, _ = _client_returning("this is not json")
        with mock.patch.object(ai, "get_client", return_value=client):
            with self.assertRaises(ai.GigsieAIError):
                ai.generate_task_brief(
                    dict(VALID_REQUEST), scope_strategy="budget_first", current_brief=GOOD_BRIEF
                )

    def test_missing_required_content_in_a_revision_raises(self) -> None:
        partial = {"title": "Only a title", "objective": "An objective"}
        client, _ = _client_returning(json.dumps(partial))
        with mock.patch.object(ai, "get_client", return_value=client):
            with self.assertRaises(ai.GigsieAIError):
                ai.generate_task_brief(
                    dict(VALID_REQUEST), scope_strategy="budget_first", current_brief=GOOD_BRIEF
                )


if __name__ == "__main__":
    unittest.main()
