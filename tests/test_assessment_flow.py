"""End-to-end checks for the Streamlit skill-assessment flow (student_ui.py).

These use Streamlit's official ``AppTest`` harness to run app.py. The model call is
mocked (no API credits) and storage is redirected to a temporary folder, so your
real ``data/`` files are never touched.

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

import assessments  # noqa: E402
import gigsie_ai  # noqa: E402
import profiles  # noqa: E402
import storage  # noqa: E402

try:
    from streamlit.testing.v1 import AppTest  # noqa: E402
except Exception:  # pragma: no cover - older Streamlit without the test API
    AppTest = None

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

# The model "returns" this. Questions have no ids, exactly like the real parser.
RAW_ASSESSMENT = {
    "skill": "Canva",
    "questions": [
        {
            "question": "What is question one?",
            "options": ["Opt A1", "Opt A2", "Opt A3", "Opt A4"],
            "correct_index": 0,
            "explanation": "EXPLANATION_ONE",
        },
        {
            "question": "What is question two?",
            "options": ["Opt B1", "Opt B2", "Opt B3", "Opt B4"],
            "correct_index": 1,
            "explanation": "EXPLANATION_TWO",
        },
        {
            "question": "What is question three?",
            "options": ["Opt C1", "Opt C2", "Opt C3", "Opt C4"],
            "correct_index": 2,
            "explanation": "EXPLANATION_THREE",
        },
    ],
}

# A deliberately mixed set: two right, one wrong -> 2 / 3.
CHOSEN = [0, 1, 0]

GENERATED = {"assessment": RAW_ASSESSMENT, "problems": [], "raw": "{}"}

PROFILE_VALUES = {
    "display_name": "Asha Rao",
    "skills": "Canva\nCopywriting",
    "experience_level": "Beginner",
    "bio": "Second-year student.",
    "portfolio_links": ["https://example.com/asha"],
    "weekly_hours": 10,
}


def _by_label(widgets, label: str):
    for widget in widgets:
        if getattr(widget, "label", None) == label:
            return widget
    raise AssertionError(f"widget with label {label!r} was not found")


def _page_text(at) -> str:
    parts = []
    for name in (
        "markdown",
        "caption",
        "text",
        "info",
        "warning",
        "error",
        "success",
        "subheader",
        "header",
    ):
        for element in getattr(at, name, []) or []:
            parts.append(str(getattr(element, "value", "")))
    return "\n".join(parts)


@unittest.skipUnless(AppTest is not None, "streamlit.testing.v1 is not available")
class AssessmentFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        patchers = [
            mock.patch.object(storage, "DATA_DIR", self.data_dir),
            mock.patch.object(storage, "seed_samples_on_first_run", return_value=[]),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.profile = profiles.save_profile(PROFILE_VALUES, data_dir=self.data_dir)

    def _open_student_with_profile(self):
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        _by_label(at.button, "Enter the student area").click().run()
        self.assertFalse(at.exception)
        _by_label(at.button, "Load this profile").click().run()
        self.assertFalse(at.exception)
        return at

    def _generate_and_start(self, at):
        _by_label(at.button, "Generate practice assessment").click().run()
        self.assertFalse(at.exception)
        _by_label(at.button, "Start assessment").click().run()
        self.assertFalse(at.exception)
        return at

    def _answer_and_submit(self, at, chosen=None):
        chosen = CHOSEN if chosen is None else chosen
        radios = at.radio
        self.assertEqual(len(radios), len(chosen))
        for radio, value in zip(radios, chosen):
            radio.set_value(value)
        _by_label(at.button, "Submit answers").click().run()
        self.assertFalse(at.exception)
        return at

    # --- generation -------------------------------------------------------
    def test_generate_shows_a_start_button(self) -> None:
        with mock.patch.object(gigsie_ai, "generate_assessment", return_value=GENERATED):
            at = self._open_student_with_profile()
            _by_label(at.button, "Generate practice assessment").click().run()
            self.assertFalse(at.exception)
            self.assertIn("Start assessment", [b.label for b in at.button])
            self.assertIn("Canva", _page_text(at))

    def test_answer_key_is_hidden_before_submission(self) -> None:
        with mock.patch.object(gigsie_ai, "generate_assessment", return_value=GENERATED):
            at = self._open_student_with_profile()
            self._generate_and_start(at)
            text = _page_text(at)
            self.assertIn("What is question one?", text)
            # No explanation and no "correct answer" hint may appear yet.
            self.assertNotIn("EXPLANATION_ONE", text)
            self.assertNotIn("correct answer", text.lower())

    def test_generation_failure_shows_an_error_and_no_assessment(self) -> None:
        with mock.patch.object(
            gigsie_ai, "generate_assessment", side_effect=gigsie_ai.GigsieAIError("model down")
        ):
            at = self._open_student_with_profile()
            _by_label(at.button, "Generate practice assessment").click().run()
            self.assertFalse(at.exception)
            self.assertTrue(any("could not be generated" in e.value for e in at.error))
            self.assertNotIn("Start assessment", [b.label for b in at.button])

    # --- grading and saving ----------------------------------------------
    def test_full_flow_scores_and_saves(self) -> None:
        with mock.patch.object(gigsie_ai, "generate_assessment", return_value=GENERATED):
            at = self._open_student_with_profile()
            self._generate_and_start(at)
            self._answer_and_submit(at)

        saved = storage.load_assessments(self.data_dir)
        self.assertEqual(len(saved), 1)
        record = saved[0]
        self.assertEqual(record["profile_id"], self.profile["id"])
        self.assertEqual(record["skill"], "Canva")
        self.assertEqual(record["score"], 2)
        self.assertEqual(record["max_score"], 3)
        self.assertEqual(record["percent"], 67)
        self.assertEqual(record["result_type"], assessments.RESULT_TYPE)

        text = _page_text(at)
        self.assertIn("EXPLANATION_ONE", text)
        self.assertIn("correct answer", text.lower())

    def test_rerun_does_not_duplicate_the_result(self) -> None:
        with mock.patch.object(gigsie_ai, "generate_assessment", return_value=GENERATED):
            at = self._open_student_with_profile()
            self._generate_and_start(at)
            self._answer_and_submit(at)
            at.run()
            at.run()
        self.assertEqual(len(storage.load_assessments(self.data_dir)), 1)

    def test_unanswered_question_is_counted_incorrect(self) -> None:
        with mock.patch.object(gigsie_ai, "generate_assessment", return_value=GENERATED):
            at = self._open_student_with_profile()
            self._generate_and_start(at)
            # Answer only the first question correctly and leave the rest blank.
            at.radio[0].set_value(0)
            _by_label(at.button, "Submit answers").click().run()

        record = storage.load_assessments(self.data_dir)[0]
        self.assertEqual(record["score"], 1)
        self.assertEqual(record["unanswered"], 2)

    def test_storage_failure_does_not_claim_success(self) -> None:
        with mock.patch.object(gigsie_ai, "generate_assessment", return_value=GENERATED):
            at = self._open_student_with_profile()
            self._generate_and_start(at)
            with mock.patch.object(
                storage, "save_assessments", side_effect=storage.StorageError("disk full")
            ):
                self._answer_and_submit(at)

        # No metric (result view) and no saved file, but a clear error instead.
        self.assertTrue(any("could not be saved" in e.value for e in at.error))
        self.assertEqual([m.value for m in at.metric], [])
        self.assertFalse((self.data_dir / "assessments.json").exists())

    # --- history and profile scoping -------------------------------------
    def test_history_is_filtered_to_the_active_profile(self) -> None:
        assessment = assessments.prepare_assessment(RAW_ASSESSMENT)
        grade = assessments.grade(assessment, {"q1": 0, "q2": 1, "q3": 2})
        assessments.save_result(
            assessments.build_result("Canva", self.profile["id"], assessment, grade),
            data_dir=self.data_dir,
        )
        assessments.save_result(
            assessments.build_result("Zookeeping", "p_someone_else", assessment, grade),
            data_dir=self.data_dir,
        )

        at = self._open_student_with_profile()
        text = _page_text(at)
        self.assertIn("Canva", text)
        self.assertIn("Assessment history", text)
        self.assertNotIn("Zookeeping", text)

    def test_assessment_does_not_block_applying(self) -> None:
        # With one gig present, the apply button is still offered to the student.
        storage.save_gigs(
            [{"id": "g_1", "title": "Design posts", "required_skills": ["Canva"], "sample": False}],
            data_dir=self.data_dir,
        )
        with mock.patch.object(gigsie_ai, "generate_assessment", return_value=GENERATED):
            at = self._open_student_with_profile()
        self.assertIn("Review proposal", [b.label for b in at.button])


if __name__ == "__main__":
    unittest.main()
