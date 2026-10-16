"""Structured practice skill assessments.

Division of labour:
  * The AI (``gigsie_ai.generate_assessment``) *suggests* questions in a fixed
    JSON shape.
  * This module *validates* that shape before the assessment is shown, keeps the
    answer key hidden until submission, and *scores* the answers in plain Python.

Important, honest labelling: these are AI-generated **practice** results. They
are not certifications and not independently verified credentials. Completing
(or skipping) an assessment never blocks a student from applying for a gig.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import storage
import validation

MIN_QUESTIONS = 3
MAX_QUESTIONS = 6
MIN_OPTIONS = 2

RESULT_TYPE = "ai_generated_practice_assessment"
DISCLAIMER = (
    "AI-generated practice result. This is not a certification and not an "
    "independently verified credential - it is a self-practice score only."
)

# Shown next to every score so the marking is never a mystery.
SCORING_NOTE = (
    "Each question is worth one point. Unanswered questions are counted as "
    "incorrect, so the score is (correct answers) out of (total questions)."
)


def _new_id() -> str:
    """A fresh id for a stored result."""
    return f"as_{uuid4().hex[:8]}"


def new_assessment_id() -> str:
    """A fresh id for one assessment 'paper' (the questions, not a result)."""
    return f"asm_{uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Validating the AI's question set (before it is ever shown)
# ---------------------------------------------------------------------------
def validate_assessment(assessment: Any) -> list[dict[str, str]]:
    """Check an assessment object. Errors mean it must not be shown at all."""
    if not isinstance(assessment, dict):
        return [{"level": "error", "message": "The assessment could not be read."}]

    findings: list[dict[str, str]] = []

    skill = str(assessment.get("skill") or "").strip()
    if not skill:
        findings.append({"level": "error", "message": "The assessment does not name a skill."})

    questions = assessment.get("questions")
    if not isinstance(questions, list) or not questions:
        findings.append({"level": "error", "message": "The assessment has no questions."})
        return findings

    if not (MIN_QUESTIONS <= len(questions) <= MAX_QUESTIONS):
        findings.append(
            {
                "level": "error",
                "message": (
                    f"The assessment should have between {MIN_QUESTIONS} and "
                    f"{MAX_QUESTIONS} questions (it had {len(questions)})."
                ),
            }
        )

    for number, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            findings.append(
                {"level": "error", "message": f"Question {number} is not in the expected format."}
            )
            continue
        if not str(question.get("question") or "").strip():
            findings.append({"level": "error", "message": f"Question {number} has no text."})
        options = question.get("options")
        if not isinstance(options, list) or len(options) < MIN_OPTIONS:
            findings.append(
                {
                    "level": "error",
                    "message": f"Question {number} needs at least {MIN_OPTIONS} answer options.",
                }
            )
            continue
        index = question.get("correct_index")
        if not isinstance(index, int) or isinstance(index, bool) or not (0 <= index < len(options)):
            findings.append(
                {
                    "level": "error",
                    "message": f"Question {number} has no valid correct answer.",
                }
            )

    # Duplicate identifiers would make a student's answer ambiguous, so they are
    # always rejected rather than silently rewritten.
    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    for question in questions:
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("id") or "").strip()
        if not question_id:
            continue
        if question_id in seen_ids and question_id not in duplicate_ids:
            duplicate_ids.append(question_id)
        seen_ids.add(question_id)
    if duplicate_ids:
        findings.append(
            {
                "level": "error",
                "message": (
                    "The assessment has duplicate question identifiers: "
                    + ", ".join(duplicate_ids)
                    + "."
                ),
            }
        )

    return findings


def public_assessment(assessment: Any) -> dict[str, Any]:
    """The student-facing copy: questions and options only.

    The correct answer (``correct_index``) and the ``explanation`` are removed so
    the answer key can never leak before the student submits.
    """
    assessment = assessment if isinstance(assessment, dict) else {}
    questions = assessment.get("questions")
    questions = questions if isinstance(questions, list) else []

    public_questions: list[dict[str, Any]] = []
    for question in questions:
        if not isinstance(question, dict):
            continue
        options = question.get("options")
        options = [str(option) for option in options] if isinstance(options, list) else []
        public_questions.append(
            {
                # The identifier is safe to show: it stores the answer, it does
                # not reveal it.
                "id": str(question.get("id") or ""),
                "question": str(question.get("question") or ""),
                "options": options,
            }
        )

    return {
        "skill": str(assessment.get("skill") or ""),
        "questions": public_questions,
        "is_practice": True,
    }


# ---------------------------------------------------------------------------
# Preparing an assessment for display and storage
# ---------------------------------------------------------------------------
def question_count(assessment: Any) -> int:
    """How many questions the assessment has (0 when unreadable)."""
    questions = assessment.get("questions") if isinstance(assessment, dict) else None
    return len(questions) if isinstance(questions, list) else 0


def assign_question_ids(assessment: Any) -> dict[str, Any]:
    """Return a copy where every question has a stable, non-empty id.

    Existing ids are kept exactly as-is, so a caller-supplied duplicate is left
    in place and rejected by ``validate_assessment`` instead of being silently
    rewritten.
    """
    if not isinstance(assessment, dict):
        return {}
    questions = assessment.get("questions")
    if not isinstance(questions, list):
        return dict(assessment)

    prepared = dict(assessment)
    used = {
        str(question.get("id")).strip()
        for question in questions
        if isinstance(question, dict) and str(question.get("id") or "").strip()
    }

    result: list[Any] = []
    for number, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            result.append(question)
            continue
        copy = dict(question)
        question_id = str(copy.get("id") or "").strip()
        if not question_id:
            question_id = f"q{number}"
            counter = 1
            while question_id in used:
                counter += 1
                question_id = f"q{number}_{counter}"
            copy["id"] = question_id
        used.add(question_id)
        result.append(copy)

    prepared["questions"] = result
    return prepared


def prepare_assessment(assessment: Any, skill: Any = None) -> dict[str, Any]:
    """Finalize a raw assessment for display and storage.

    Assigns an assessment id, fills in the skill when the model left it blank,
    and gives every question a stable id. This does NOT check validity - always
    call ``validate_assessment`` on the result before showing it.
    """
    if not isinstance(assessment, dict):
        return {}
    prepared = assign_question_ids(assessment)
    prepared["skill"] = str(prepared.get("skill") or skill or "").strip()
    if not str(prepared.get("id") or "").strip():
        prepared["id"] = new_assessment_id()
    return prepared


# ---------------------------------------------------------------------------
# Deterministic scoring
# ---------------------------------------------------------------------------
def _answer_for(answers: dict[Any, Any], question_id: str, position: int) -> Any:
    """Look up a submitted answer by question id first, then by position."""
    for key in (question_id, str(position), position):
        if key is None or key == "":
            continue
        try:
            if key in answers:
                return answers[key]
        except TypeError:
            continue
    return None


def _as_index(value: Any) -> int | None:
    """Coerce a submitted answer into a non-negative option index, or None."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    return index if index >= 0 else None


def validate_answers(assessment: Any, answers: Any) -> list[dict[str, str]]:
    """Check submitted answers before grading.

    Returns findings; an error blocks grading. Unanswered questions are allowed -
    ``grade`` simply marks them incorrect.
    """
    if not isinstance(answers, dict):
        return [{"level": "error", "message": "The submitted answers could not be read."}]

    questions = assessment.get("questions") if isinstance(assessment, dict) else None
    questions = questions if isinstance(questions, list) else []
    if not questions:
        return [{"level": "error", "message": "This assessment has no questions to grade."}]

    option_counts: dict[Any, int] = {}
    for position, question in enumerate(questions):
        question = question if isinstance(question, dict) else {}
        options = question.get("options")
        option_count = len(options) if isinstance(options, list) else 0
        question_id = str(question.get("id") or "").strip()
        if question_id:
            option_counts[question_id] = option_count
        option_counts[str(position)] = option_count

    findings: list[dict[str, str]] = []
    for key, value in answers.items():
        lookup: Any = None
        if key in option_counts:
            lookup = key
        elif str(key) in option_counts:
            lookup = str(key)

        if lookup is None:
            findings.append(
                {
                    "level": "error",
                    "message": (
                        "An answer was submitted for a question that is not part of "
                        f"this assessment ('{key}')."
                    ),
                }
            )
            continue
        if value is None or value == "":
            continue

        index = _as_index(value)
        if index is None:
            findings.append(
                {"level": "error", "message": "One of the submitted answers is not a valid choice."}
            )
            continue
        if not (0 <= index < option_counts[lookup]):
            findings.append(
                {
                    "level": "error",
                    "message": "One of the submitted answers is outside the available choices.",
                }
            )
    return findings


def grade(assessment: Any, answers: Any) -> dict[str, Any]:
    """Score ``answers`` against ``assessment``. Pure Python, no AI.

    ``answers`` maps a question ``id`` to the chosen option index; a bare position
    (int or numeric string) is also accepted for convenience. Missing, blank, or
    out-of-range answers are simply marked incorrect.
    """
    questions = assessment.get("questions") if isinstance(assessment, dict) else None
    questions = questions if isinstance(questions, list) else []
    answers = answers if isinstance(answers, dict) else {}

    review: list[dict[str, Any]] = []
    score = 0
    answered_count = 0

    for position, question in enumerate(questions):
        question = question if isinstance(question, dict) else {}
        options = question.get("options")
        options = [str(option) for option in options] if isinstance(options, list) else []
        correct_index = question.get("correct_index")
        question_id = str(question.get("id") or "").strip()

        selected = _as_index(_answer_for(answers, question_id, position))
        answered = selected is not None
        if answered:
            answered_count += 1

        is_correct = (
            answered
            and isinstance(correct_index, int)
            and not isinstance(correct_index, bool)
            and selected == correct_index
        )
        if is_correct:
            score += 1

        review.append(
            {
                "id": question_id,
                "question": str(question.get("question") or ""),
                "options": options,
                "selected_index": selected,
                "correct_index": correct_index,
                "correct_option": (
                    options[correct_index]
                    if isinstance(correct_index, int)
                    and not isinstance(correct_index, bool)
                    and 0 <= correct_index < len(options)
                    else ""
                ),
                "is_correct": is_correct,
                "answered": answered,
                "explanation": str(question.get("explanation") or ""),
            }
        )

    max_score = len(questions)
    percent = round(100 * score / max_score) if max_score else 0

    return {
        "score": score,
        "max_score": max_score,
        "percent": percent,
        "answered": answered_count,
        "unanswered": max_score - answered_count,
        "review": review,
    }


def score_label(percent: Any) -> str:
    """A short, non-flattering label for a practice score."""
    if not isinstance(percent, (int, float)):
        return "Not scored"
    if percent >= 80:
        return "Strong"
    if percent >= 50:
        return "Getting there"
    return "Needs more practice"


# ---------------------------------------------------------------------------
# Storing results
# ---------------------------------------------------------------------------
def build_result(
    skill: Any,
    profile_id: Any,
    assessment: Any,
    grade_result: dict[str, Any],
    started_at: Any = None,
    answers: Any = None,
) -> dict[str, Any]:
    """Assemble a storable practice result.

    Stores the minimum needed to retrieve and review the result: who (profile_id),
    which skill, which assessment, the deterministic score, and the per-question
    review (so explanations can be shown again from history).
    """
    completed = datetime.now(timezone.utc)
    assessment = assessment if isinstance(assessment, dict) else {}

    duration_seconds: int | None = None
    if isinstance(started_at, datetime):
        start = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
        duration_seconds = max(0, int((completed - start).total_seconds()))

    skill_name = str(skill or "").strip() or str(assessment.get("skill") or "").strip()

    return {
        "id": _new_id(),
        "profile_id": profile_id,
        "skill": skill_name,
        "assessment_id": str(assessment.get("id") or ""),
        "score": int(grade_result.get("score", 0)),
        "max_score": int(grade_result.get("max_score", 0)),
        "percent": int(grade_result.get("percent", 0)),
        "answered": int(grade_result.get("answered", 0)),
        "unanswered": int(grade_result.get("unanswered", 0)),
        "answers": dict(answers) if isinstance(answers, dict) else {},
        "review": list(grade_result.get("review") or []),
        "started_at": started_at.isoformat(timespec="seconds") if isinstance(started_at, datetime) else "",
        "completed_at": completed.isoformat(timespec="seconds"),
        "duration_seconds": duration_seconds,
        "result_type": RESULT_TYPE,
        "ai_assisted": True,
        "disclaimer": DISCLAIMER,
        "scoring_note": SCORING_NOTE,
        "created_at": storage.now_iso(),
    }


def save_result(result: dict[str, Any], data_dir: Any = None) -> dict[str, Any]:
    """Append one practice-assessment result to local storage."""
    results = storage.load_assessments(data_dir)
    record = dict(result)
    record.setdefault("id", _new_id())
    record.setdefault("created_at", storage.now_iso())
    record.setdefault("result_type", RESULT_TYPE)
    record.setdefault("disclaimer", DISCLAIMER)
    results.append(record)
    storage.save_assessments(results, data_dir)
    return record


def all_results(data_dir: Any = None) -> list[dict[str, Any]]:
    return storage.load_assessments(data_dir)


def results_for_profile(profile_id: Any, data_dir: Any = None) -> list[dict[str, Any]]:
    return [
        result
        for result in storage.load_assessments(data_dir)
        if result.get("profile_id") == profile_id
    ]


def has_errors(findings: Any) -> bool:
    """Convenience wrapper so callers can reuse validation.has_errors."""
    return validation.has_errors(findings)
