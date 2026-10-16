"""Unit tests for assessments.py (validation, answer protection, scoring, storage).

No Streamlit and no API call: the model call is mocked and storage is redirected to
a temporary folder, so your real ``data/`` files are never touched and no API
credits are spent.

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import assessments  # noqa: E402
import gigsie_ai  # noqa: E402
import storage  # noqa: E402
import validation  # noqa: E402

# Field names that must never appear in the student-facing copy.
FORBIDDEN_PUBLIC_KEYS = {
    "correct_index",
    "correct_option",
    "explanation",
    "is_correct",
    "answer",
    "answer_key",
    "selected_index",
}


def _raw_assessment(skill: str = "Canva", count: int = 3, options_per: int = 4) -> dict:
    """A well-formed assessment with no ids, as the model would return it."""
    questions = []
    for number in range(count):
        questions.append(
            {
                "question": f"Question {number + 1} about {skill}?",
                "options": [f"Option {number}-{letter}" for letter in range(options_per)],
                "correct_index": number % options_per,
                "explanation": f"Because reason {number + 1}.",
            }
        )
    return {"skill": skill, "questions": questions}


def _prepared(**kwargs) -> dict:
    return assessments.prepare_assessment(_raw_assessment(**kwargs))


def _all_keys(value) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys |= _all_keys(item)
    elif isinstance(value, list):
        for item in value:
            keys |= _all_keys(item)
    return keys


class ValidateAssessmentTests(unittest.TestCase):
    def test_prepared_assessment_is_valid(self) -> None:
        findings = assessments.validate_assessment(_prepared())
        self.assertFalse(validation.has_errors(findings), findings)

    def test_missing_skill_is_an_error(self) -> None:
        assessment = _prepared()
        assessment["skill"] = ""
        self.assertTrue(validation.has_errors(assessments.validate_assessment(assessment)))

    def test_missing_questions_is_an_error(self) -> None:
        self.assertTrue(
            validation.has_errors(assessments.validate_assessment({"skill": "Canva"}))
        )

    def test_too_few_questions_is_an_error(self) -> None:
        assessment = _prepared(count=2)
        self.assertTrue(validation.has_errors(assessments.validate_assessment(assessment)))

    def test_too_many_questions_is_an_error(self) -> None:
        assessment = _prepared(count=assessments.MAX_QUESTIONS + 1)
        self.assertTrue(validation.has_errors(assessments.validate_assessment(assessment)))

    def test_question_without_text_is_an_error(self) -> None:
        assessment = _prepared()
        assessment["questions"][0]["question"] = ""
        self.assertTrue(validation.has_errors(assessments.validate_assessment(assessment)))

    def test_question_with_too_few_options_is_an_error(self) -> None:
        assessment = _prepared()
        assessment["questions"][0]["options"] = ["only one"]
        assessment["questions"][0]["correct_index"] = 0
        self.assertTrue(validation.has_errors(assessments.validate_assessment(assessment)))

    def test_correct_index_out_of_range_is_an_error(self) -> None:
        assessment = _prepared()
        assessment["questions"][0]["correct_index"] = 99
        self.assertTrue(validation.has_errors(assessments.validate_assessment(assessment)))

    def test_negative_correct_index_is_an_error(self) -> None:
        assessment = _prepared()
        assessment["questions"][0]["correct_index"] = -1
        self.assertTrue(validation.has_errors(assessments.validate_assessment(assessment)))

    def test_boolean_correct_index_is_an_error(self) -> None:
        assessment = _prepared()
        assessment["questions"][0]["correct_index"] = True
        self.assertTrue(validation.has_errors(assessments.validate_assessment(assessment)))

    def test_non_integer_correct_index_is_an_error(self) -> None:
        assessment = _prepared()
        assessment["questions"][0]["correct_index"] = "0"
        self.assertTrue(validation.has_errors(assessments.validate_assessment(assessment)))

    def test_duplicate_question_ids_are_rejected(self) -> None:
        assessment = _prepared()
        assessment["questions"][0]["id"] = "dup"
        assessment["questions"][1]["id"] = "dup"
        findings = assessments.validate_assessment(assessment)
        self.assertTrue(validation.has_errors(findings))
        self.assertTrue(any("duplicate question identifiers" in f["message"].lower() for f in findings))

    def test_non_dict_assessment_is_an_error(self) -> None:
        self.assertTrue(validation.has_errors(assessments.validate_assessment("nope")))


class PrepareAssessmentTests(unittest.TestCase):
    def test_assigns_unique_question_ids(self) -> None:
        prepared = _prepared()
        ids = [q["id"] for q in prepared["questions"]]
        self.assertEqual(ids, ["q1", "q2", "q3"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_keeps_existing_ids(self) -> None:
        assessment = _raw_assessment()
        assessment["questions"][0]["id"] = "custom"
        prepared = assessments.prepare_assessment(assessment)
        self.assertEqual(prepared["questions"][0]["id"], "custom")

    def test_assign_question_ids_does_not_rewrite_duplicates(self) -> None:
        # Duplicates must survive so that validate_assessment can reject them.
        assessment = _raw_assessment()
        assessment["questions"][0]["id"] = "same"
        assessment["questions"][1]["id"] = "same"
        prepared = assessments.assign_question_ids(assessment)
        self.assertEqual(prepared["questions"][0]["id"], "same")
        self.assertEqual(prepared["questions"][1]["id"], "same")

    def test_assigns_assessment_id_and_skill_fallback(self) -> None:
        prepared = assessments.prepare_assessment({"questions": _raw_assessment()["questions"]}, "Canva")
        self.assertTrue(prepared["id"].startswith("asm_"))
        self.assertEqual(prepared["skill"], "Canva")

    def test_question_count(self) -> None:
        self.assertEqual(assessments.question_count(_prepared()), 3)
        self.assertEqual(assessments.question_count({}), 0)
        self.assertEqual(assessments.question_count("nope"), 0)


class PublicAssessmentTests(unittest.TestCase):
    def test_public_copy_hides_the_answer_key(self) -> None:
        private = _prepared()
        public = assessments.public_assessment(private)
        leaked = _all_keys(public) & FORBIDDEN_PUBLIC_KEYS
        self.assertEqual(leaked, set(), leaked)

    def test_public_copy_has_questions_options_and_ids(self) -> None:
        public = assessments.public_assessment(_prepared())
        self.assertTrue(public["is_practice"])
        self.assertEqual(len(public["questions"]), 3)
        for question in public["questions"]:
            self.assertTrue(question["id"])
            self.assertTrue(question["question"])
            self.assertEqual(len(question["options"]), 4)

    def test_public_copy_of_unreadable_input_is_empty(self) -> None:
        self.assertEqual(assessments.public_assessment(None)["questions"], [])


class GradeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assessment = _prepared(count=4)

    def _correct_answers(self) -> dict:
        return {
            q["id"]: q["correct_index"] for q in self.assessment["questions"]
        }

    def test_all_correct_scores_full_marks(self) -> None:
        result = assessments.grade(self.assessment, self._correct_answers())
        self.assertEqual(result["score"], 4)
        self.assertEqual(result["max_score"], 4)
        self.assertEqual(result["percent"], 100)
        self.assertEqual(result["unanswered"], 0)
        self.assertTrue(all(item["is_correct"] for item in result["review"]))

    def test_wrong_answers_are_marked_incorrect(self) -> None:
        answers = self._correct_answers()
        first_id = self.assessment["questions"][0]["id"]
        # Choose an option that is definitely not the correct one.
        answers[first_id] = (answers[first_id] + 1) % 4
        result = assessments.grade(self.assessment, answers)
        self.assertEqual(result["score"], 3)
        self.assertEqual(result["percent"], 75)
        self.assertFalse(result["review"][0]["is_correct"])

    def test_unanswered_questions_are_counted_incorrect(self) -> None:
        result = assessments.grade(self.assessment, {})
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["unanswered"], 4)
        self.assertEqual(result["answered"], 0)
        self.assertTrue(all(not item["answered"] for item in result["review"]))

    def test_blank_answer_is_treated_as_unanswered(self) -> None:
        answers = self._correct_answers()
        answers[self.assessment["questions"][0]["id"]] = None
        result = assessments.grade(self.assessment, answers)
        self.assertEqual(result["score"], 3)
        self.assertEqual(result["unanswered"], 1)

    def test_answers_keyed_by_position_still_work(self) -> None:
        answers = {index: q["correct_index"] for index, q in enumerate(self.assessment["questions"])}
        result = assessments.grade(self.assessment, answers)
        self.assertEqual(result["score"], 4)

    def test_out_of_range_answer_is_incorrect(self) -> None:
        answers = self._correct_answers()
        answers[self.assessment["questions"][0]["id"]] = 99
        result = assessments.grade(self.assessment, answers)
        self.assertEqual(result["score"], 3)
        self.assertFalse(result["review"][0]["is_correct"])

    def test_non_dict_answers_score_zero_without_raising(self) -> None:
        result = assessments.grade(self.assessment, "nope")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["max_score"], 4)

    def test_percent_rounds_to_nearest_whole_number(self) -> None:
        result = assessments.grade(self.assessment, self._correct_answers())
        self.assertIsInstance(result["percent"], int)


class ValidateAnswersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assessment = _prepared(count=3)
        self.ids = [q["id"] for q in self.assessment["questions"]]

    def test_valid_answers_pass(self) -> None:
        findings = assessments.validate_answers(self.assessment, {self.ids[0]: 0})
        self.assertFalse(validation.has_errors(findings), findings)

    def test_non_dict_answers_is_an_error(self) -> None:
        self.assertTrue(validation.has_errors(assessments.validate_answers(self.assessment, "x")))

    def test_unknown_question_key_is_an_error(self) -> None:
        findings = assessments.validate_answers(self.assessment, {"nope": 0})
        self.assertTrue(validation.has_errors(findings))

    def test_out_of_range_choice_is_an_error(self) -> None:
        findings = assessments.validate_answers(self.assessment, {self.ids[0]: 99})
        self.assertTrue(validation.has_errors(findings))

    def test_non_numeric_choice_is_an_error(self) -> None:
        findings = assessments.validate_answers(self.assessment, {self.ids[0]: "banana"})
        self.assertTrue(validation.has_errors(findings))

    def test_blank_answer_is_allowed(self) -> None:
        findings = assessments.validate_answers(self.assessment, {self.ids[0]: None, self.ids[1]: ""})
        self.assertFalse(validation.has_errors(findings), findings)

    def test_assessment_without_questions_is_an_error(self) -> None:
        findings = assessments.validate_answers({"skill": "x", "questions": []}, {})
        self.assertTrue(validation.has_errors(findings))


class ScoreLabelTests(unittest.TestCase):
    def test_thresholds(self) -> None:
        self.assertEqual(assessments.score_label(100), "Strong")
        self.assertEqual(assessments.score_label(80), "Strong")
        self.assertEqual(assessments.score_label(50), "Getting there")
        self.assertEqual(assessments.score_label(49), "Needs more practice")
        self.assertEqual(assessments.score_label("x"), "Not scored")


class ResultStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.assessment = _prepared(skill="Canva", count=4)
        self.grade = assessments.grade(
            self.assessment,
            {q["id"]: q["correct_index"] for q in self.assessment["questions"]},
        )

    def _build(self, profile_id: str = "p_test0001", skill: str = "Canva") -> dict:
        return assessments.build_result(
            skill, profile_id, self.assessment, self.grade, answers={"q1": 0}
        )

    def test_build_result_contains_the_required_fields(self) -> None:
        result = self._build()
        for key in (
            "id",
            "profile_id",
            "skill",
            "assessment_id",
            "score",
            "max_score",
            "percent",
            "completed_at",
            "result_type",
        ):
            self.assertIn(key, result)
        self.assertEqual(result["profile_id"], "p_test0001")
        self.assertEqual(result["assessment_id"], self.assessment["id"])
        self.assertEqual(result["percent"], 100)
        self.assertEqual(result["result_type"], assessments.RESULT_TYPE)
        self.assertIn("disclaimer", result)
        self.assertIn("scoring_note", result)
        self.assertTrue(result["ai_assisted"])

    def test_save_and_retrieve_result(self) -> None:
        saved = assessments.save_result(self._build(), data_dir=self.data_dir)
        stored = storage.load_assessments(self.data_dir)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["id"], saved["id"])

    def test_results_are_filtered_by_profile_id(self) -> None:
        assessments.save_result(self._build(profile_id="p_alice"), data_dir=self.data_dir)
        assessments.save_result(self._build(profile_id="p_bob"), data_dir=self.data_dir)
        alice = assessments.results_for_profile("p_alice", self.data_dir)
        self.assertEqual(len(alice), 1)
        self.assertEqual(alice[0]["profile_id"], "p_alice")
        self.assertEqual(assessments.results_for_profile("p_missing", self.data_dir), [])

    def test_all_results_returns_everything(self) -> None:
        assessments.save_result(self._build(profile_id="p_alice"), data_dir=self.data_dir)
        assessments.save_result(self._build(profile_id="p_bob"), data_dir=self.data_dir)
        self.assertEqual(len(assessments.all_results(self.data_dir)), 2)

    def test_two_saves_create_two_records(self) -> None:
        assessments.save_result(self._build(), data_dir=self.data_dir)
        assessments.save_result(self._build(), data_dir=self.data_dir)
        self.assertEqual(len(storage.load_assessments(self.data_dir)), 2)

    def test_storage_failure_is_reported(self) -> None:
        blocked = Path(self._tmp.name) / "blocked_file"
        blocked.write_text("not a directory", encoding="utf-8")
        with self.assertRaises(storage.StorageError):
            assessments.save_result(self._build(), data_dir=blocked)


class GenerateAssessmentTests(unittest.TestCase):
    """The model call is mocked - no network, no API credits."""

    def test_successful_generation_is_validated(self) -> None:
        raw = json.dumps(_raw_assessment())
        with mock.patch.object(gigsie_ai, "_call_model", return_value=raw):
            generated = gigsie_ai.generate_assessment("Canva")
        prepared = assessments.prepare_assessment(generated["assessment"], "Canva")
        self.assertFalse(validation.has_errors(assessments.validate_assessment(prepared)))

    def test_malformed_model_output_raises(self) -> None:
        # Missing questions entirely.
        raw = json.dumps({"skill": "Canva"})
        with mock.patch.object(gigsie_ai, "_call_model", return_value=raw):
            with self.assertRaises(gigsie_ai.GigsieAIError):
                gigsie_ai.generate_assessment("Canva")

    def test_non_json_model_output_raises(self) -> None:
        with mock.patch.object(gigsie_ai, "_call_model", return_value="not json at all"):
            with self.assertRaises(gigsie_ai.GigsieAIError):
                gigsie_ai.generate_assessment("Canva")

    def test_network_failure_raises(self) -> None:
        with mock.patch.object(
            gigsie_ai, "_call_model", side_effect=gigsie_ai.GigsieAIError("network down")
        ):
            with self.assertRaises(gigsie_ai.GigsieAIError):
                gigsie_ai.generate_assessment("Canva")

    def test_empty_skill_raises_without_calling_the_model(self) -> None:
        with mock.patch.object(gigsie_ai, "_call_model") as fake:
            with self.assertRaises(gigsie_ai.GigsieAIError):
                gigsie_ai.generate_assessment("   ")
            fake.assert_not_called()

    def test_parse_assessment_drops_unknown_fields(self) -> None:
        payload = _raw_assessment()
        payload["questions"][0]["leaked_answer"] = "secret"
        assessment, _problems = gigsie_ai.parse_assessment(json.dumps(payload))
        self.assertNotIn("leaked_answer", assessment["questions"][0])


if __name__ == "__main__":
    unittest.main()
