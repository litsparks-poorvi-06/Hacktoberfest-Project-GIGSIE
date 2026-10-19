"""Reproducible evaluation of the Gigsie draft-then-review workflow.

Research question
-----------------
When a business writes a short, often vague request, does Gigsie's workflow
(``gigsie_ai.generate_task_brief`` -> ``fairscope.analyze_brief`` /
``fairscope.build_passport``) produce a *structurally complete* brief, and does
FairScope correctly *detect* the cases that are genuinely underspecified?

What this measures, and what it does not
---------------------------------------
Everything reported here is an **automated structural** measurement taken from
the same deterministic helpers the product itself uses
(``fairscope.clarity_checks``, ``fairscope._is_specific``,
``fairscope._is_checkable``, ``validation.validate_brief``). No numeric
"quality", "fairness", or "accuracy" score is produced, because none of those
can be established automatically:

* whether a brief is commercially sensible is a human judgement,
* whether a price is fair is never computed by Gigsie at all,
* whether an objective is *well written* cannot be decided by a regex.

The one criterion that is treated as a right/wrong test is **detection**: a case
declares up front whether FairScope is expected to raise a finding, and the
evaluator reports whether it did. A warning is never counted as correct just
because it appeared.

Two artefacts are scored with the same rubric and kept separate:

``draft``
    The brief exactly as ``generate_task_brief`` returned it.
``reviewed``
    The Gig Passport built from that draft, which is what a student actually
    reads. FairScope does not silently rewrite the brief, so this is a real
    difference in representation rather than a second model call.

Usage
-----
Structural self-check, no API calls (safe in CI)::

    python scripts/evaluate_fairscope.py --self-check

Live run against the real Groq model, five cases, one call each::

    python scripts/evaluate_fairscope.py --live --json docs/evaluation_results.json

``--live`` requires ``GROQ_API_KEY`` in ``.env``. It prints nothing secret.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fairscope  # noqa: E402
import validation  # noqa: E402

CASES_PATH = ROOT / "data" / "evaluation_cases.json"

#: Fields the brief schema expects. Presence is a structural fact, not a quality
#: judgement.
REQUIRED_BRIEF_FIELDS = (
    "title",
    "objective",
    "deliverables",
    "required_skills",
    "clarifying_questions",
    "acceptance_criteria",
    "assumptions",
)

#: Levels that count as "FairScope noticed something worth a human's attention".
NOTICEABLE_LEVELS = {"error", "warning"}


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the evaluation cases. Pure data, no model involved."""
    data = json.loads((path or CASES_PATH).read_text(encoding="utf-8"))
    cases = data["cases"] if isinstance(data, dict) else data
    if not isinstance(cases, list) or not cases:
        raise ValueError("evaluation dataset is empty")
    return cases


# ---------------------------------------------------------------------------
# Rubric - shared by both artefacts so the comparison is like-for-like
# ---------------------------------------------------------------------------
def _section_values(passport: dict[str, Any], key: str) -> list[str]:
    section = (passport.get("sections") or {}).get(key) or {}
    value = section.get("value")
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def score_draft(request: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    """Structural measurements of the raw AI draft."""
    deliverables = [str(item) for item in (brief.get("deliverables") or [])]
    criteria = [str(item) for item in (brief.get("acceptance_criteria") or [])]
    skills = [str(item) for item in (brief.get("required_skills") or [])]
    objective = str(brief.get("objective") or "")

    findings = validation.validate_brief(request, brief)
    analysis = fairscope.analyze_brief(request, brief)
    signals = [
        finding.get("message", "")
        for finding in (analysis.get("signals") or [])
        if str(finding.get("level")) in NOTICEABLE_LEVELS
    ]

    return {
        "artefact": "draft",
        "fields_present": {
            field: bool(brief.get(field)) for field in REQUIRED_BRIEF_FIELDS
        },
        "all_required_fields_present": all(
            bool(brief.get(field)) for field in REQUIRED_BRIEF_FIELDS
        ),
        "deliverables_count": len(deliverables),
        "deliverables_specific": sum(
            1 for item in deliverables if fairscope._is_specific(item)
        ),
        "criteria_count": len(criteria),
        "criteria_checkable": sum(
            1 for item in criteria if fairscope._is_checkable(item)
        ),
        "skills_count": len(skills),
        "objective_specific": fairscope._is_specific(objective),
        "clarifying_questions_count": len(brief.get("clarifying_questions") or []),
        "budget_preserved": _budget_preserved(request, brief, analysis),
        "deadline_preserved": _deadline_preserved(request, brief, analysis),
        "noticeable_findings": [
            finding.get("message", "")
            for finding in findings
            if str(finding.get("level")) in NOTICEABLE_LEVELS
        ],
        "fairscope_signals": signals,
        "clarity_checks_flagged": [
            check.get("label", "")
            for check in (analysis.get("clarity", {}).get("checks") or [])
            if check.get("status") in (fairscope.STATUS_NEEDS, fairscope.STATUS_MISSING)
        ],
        "clarity_checks_missing": [
            check.get("label", "")
            for check in (analysis.get("clarity", {}).get("checks") or [])
            if check.get("status") == fairscope.STATUS_MISSING
        ],
        "error_level_findings": [
            finding.get("message", "")
            for finding in findings
            if str(finding.get("level")) == "error"
        ],
    }


#: The four brief concepts the reviewed scope must carry. Note that acceptance
#: criteria are represented by the passport's "definition of done" section -
#: there is no "acceptance_criteria" section, so a rubric that looked for one
#: would score every real passport as incomplete.
REVIEWED_REQUIRED = (
    "objective",
    "deliverables",
    "definition_of_done",
    "required_skills",
)


def score_reviewed(request: dict[str, Any], passport: dict[str, Any]) -> dict[str, Any]:
    """Structural measurements of the reviewed scope a student actually reads."""
    sections = passport.get("sections") or {}
    deliverables = _section_values(passport, "deliverables")
    criteria = _section_values(passport, "definition_of_done")
    objective = (sections.get("objective") or {}).get("value") or ""
    skills = _section_values(passport, "required_skills")

    unresolved = fairscope.passport_unresolved(passport)
    essential = fairscope.passport_essential_issues(passport)

    return {
        "artefact": "reviewed",
        "fields_present": {
            key: bool((sections.get(key) or {}).get("value"))
            for key in REVIEWED_REQUIRED
        },
        "all_required_fields_present": all(
            bool((sections.get(key) or {}).get("value"))
            for key in REVIEWED_REQUIRED
        ),
        "deliverables_count": len(deliverables),
        "deliverables_specific": sum(
            1 for item in deliverables if fairscope._is_specific(item)
        ),
        "criteria_count": len(criteria),
        "criteria_checkable": sum(
            1 for item in criteria if fairscope._is_checkable(item)
        ),
        "skills_count": len(skills),
        "objective_specific": fairscope._is_specific(objective),
        "clarifying_questions_count": len(_section_values(passport, "open_questions")),
        "budget_preserved": _passport_matches_request(
            passport, "budget", _request_budget(request)
        ),
        "deadline_preserved": _passport_matches_request(
            passport, "deadline", str(request.get("deadline") or "").strip()
        ),
        "unresolved_sections": list(unresolved),
        "essential_gaps": list(essential),
        "publishable": fairscope.passport_is_publishable(passport),
    }


def _request_budget(request: dict[str, Any]) -> float | None:
    try:
        return float(request.get("budget"))
    except (TypeError, ValueError):
        return None


def _numbers_match(left: Any, right: Any) -> bool:
    """Compare two amounts numerically, tolerating int/float and separators."""
    try:
        return abs(float(left) - float(right)) < 0.01
    except (TypeError, ValueError):
        pass
    digits_left = "".join(ch for ch in str(left) if ch.isdigit())
    digits_right = "".join(ch for ch in str(right) if ch.isdigit())
    return bool(digits_left) and digits_left == digits_right


def _passport_matches_request(
    passport: dict[str, Any], key: str, expected: Any
) -> bool:
    """True when the passport does not contradict the original request.

    An absent value is not a contradiction: the original request is the source
    of truth and Gigsie never overwrites it.
    """
    section = (passport.get("sections") or {}).get(key) or {}
    if section.get("needs_clarification") or section.get("value") in (None, ""):
        return True
    if expected in (None, ""):
        return True
    return _numbers_match(section.get("value"), expected)


def _budget_preserved(
    request: dict[str, Any], brief: dict[str, Any], analysis: dict[str, Any]
) -> bool:
    """True when nothing in the analysis suggests the stated budget was changed."""
    for finding in list(analysis.get("signals") or []) + list(
        (analysis.get("clarity", {}) or {}).get("checks") or []
    ):
        text = str(finding.get("message") or finding.get("detail") or "").lower()
        if "budget" in text and ("chang" in text or "ignor" in text or "overrid" in text):
            return False
    # A brief may restate the budget, but it must not contradict it.
    """True when nothing in the brief contradicts the stated budget."""
    expected_budget = _request_budget(request)
    for candidate in ("INR", "Rs.", "rupees", "₹"):
        blob = json.dumps(brief, default=str).replace(candidate, " ")
    if expected_budget is None:
        return True
    mentioned = set()
    import re

    for value in re.findall(r"(?:inr|rs\.?|rupees|₹)\s*([\d,]{3,})", blob, re.I):
        cleaned = "".join(ch for ch in value if ch.isdigit())
        if cleaned:
            mentioned.add(float(cleaned))
    return all(_numbers_match(amount, expected_budget) for amount in mentioned)


def _deadline_preserved(
    request: dict[str, Any], brief: dict[str, Any], analysis: dict[str, Any]
) -> bool:
    """True when the brief does not contradict the deadline the business stated.

    Preservation is deliberately *not* defined as "the brief repeats the
    deadline": Gigsie keeps the original request as the source of truth and
    never overwrites it, so a brief that simply does not mention the deadline has
    not lost it. Only a different duration counts as a contradiction.
    """
    stated = str(request.get("deadline") or "").strip()
    if not stated:
        # Nothing was stated, so nothing could have been lost or changed.
        return True

    for finding in list(analysis.get("signals") or []):
        text = str(finding.get("message") or "").lower()
        if "deadline" in text and ("chang" in text or "ignor" in text or "move" in text):
            return False

    expected_days = validation.extract_days(stated)
    if expected_days is None:
        # A non-numeric deadline ("end of the month") is not machine-comparable,
        # so only an explicit contradiction check applies - and none was found.
        return True

    claimed = {
        days
        for days in (
            validation.extract_days(str(finding))
            for finding in _brief_duration_claims(brief)
        )
        if days is not None
    }
    return not (claimed - {expected_days})


def _brief_duration_claims(brief: dict[str, Any]) -> list[str]:
    """Any duration-looking phrase the brief states, for contradiction checks."""
    import re

    blob = json.dumps(brief, default=str)
    return re.findall(r"\b\d+\s*(?:day|days|week|weeks|month|months)\b", blob, re.I)


# ---------------------------------------------------------------------------
# Case evaluation
# ---------------------------------------------------------------------------
def evaluate_case(
    case: dict[str, Any],
    brief: dict[str, Any],
    problems: list[str] | None = None,
) -> dict[str, Any]:
    """Score one case on both artefacts and judge the detection criterion."""
    request = case["request"]
    analysis = fairscope.analyze_brief(request, brief)
    passport = fairscope.build_passport(brief, request, analysis)

    draft = score_draft(request, brief)
    reviewed = score_reviewed(request, passport)

    # Two different things are measured, and they must not be conflated:
    #
    #   gap        - a required field is absent (a `missing` clarity check, an
    #                error-level finding, or an unresolved passport section).
    #                This is what the detection criterion scores.
    #   advisories - FairScope's prompts to look closer (`needs_clarification`
    #                and warning-level signals). Real briefs draw these almost
    #                every time, so counting them as failures would make the
    #                measurement meaningless. They are reported, never scored.
    gap_detected = bool(
        draft["clarity_checks_missing"]
        or draft["error_level_findings"]
        or reviewed["unresolved_sections"]
    )
    advisories = (
        list(draft["clarity_checks_flagged"])
        + list(draft["fairscope_signals"])
    )

    expected = bool(case.get("expect_detection"))
    if expected:
        detection_correct = gap_detected
        detection_label = "true_positive" if gap_detected else "false_negative"
    else:
        detection_correct = not gap_detected
        detection_label = "true_negative" if not gap_detected else "false_positive"

    return {
        "id": case["id"],
        "scenario": case["scenario"],
        "note": case.get("note", ""),
        "model_parse_problems": list(problems or []),
        "draft": draft,
        "reviewed": reviewed,
        "detection": {
            "expected": expected,
            "gap_detected": gap_detected,
            "correct": detection_correct,
            "label": detection_label,
            "reason": case.get("expect_reason", ""),
        },
        "advisories_not_scored": advisories,
    }


def generate_brief_live(request: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """One real Groq call. Returns ``(result, parse_problems)``."""
    from gigsie_ai import GigsieAIError, generate_task_brief

    try:
        result = generate_task_brief(dict(request))
    except GigsieAIError as error:
        return {"brief": {}}, [f"model call failed: {error}"]
    return result, list(result.get("problems") or [])


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def summarise(results: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [row for row in results if row.get("live")]
    if not scored:
        return {
            "cases_measured": 0,
            "note": (
                "No model-backed results in this run. Detection and preservation "
                "rates are only meaningful for a live run."
            ),
        }

    def rate(field: str, artefact: str) -> float:
        return round(
            100.0
            * sum(1 for row in scored if row[artefact].get(field))
            / len(scored),
            1,
        )

    detection = [row["detection"] for row in scored]
    return {
        "cases_measured": len(scored),
        "draft_all_fields_present_pct": rate("all_required_fields_present", "draft"),
        "reviewed_all_fields_present_pct": rate("all_required_fields_present", "reviewed"),
        "draft_budget_preserved_pct": rate("budget_preserved", "draft"),
        "reviewed_budget_preserved_pct": rate("budget_preserved", "reviewed"),
        "draft_deadline_preserved_pct": rate("deadline_preserved", "draft"),
        "reviewed_deadline_preserved_pct": rate("deadline_preserved", "reviewed"),
        "detection_correct": sum(1 for d in detection if d["correct"]),
        "detection_total": len(detection),
        "true_positives": sum(1 for d in detection if d["label"] == "true_positive"),
        "true_negatives": sum(1 for d in detection if d["label"] == "true_negative"),
    }


def print_report(results: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    print("=" * 74)
    print("Gigsie FairScope evaluation - automated structural measurements only")
    print("=" * 74)
    for row in results:
        det = row["detection"]
        mark = "PASS" if det["correct"] else "MISS"
        print(f"\n[{mark}] {row['id']}  ({row['scenario']})")
        print(
            f"      draft   : fields={row['draft']['all_required_fields_present']}"
            f"  deliverables={row['draft']['deliverables_count']}"
            f" (specific {row['draft']['deliverables_specific']})"
            f"  criteria_checkable={row['draft']['criteria_checkable']}"
        )
        print(
            f"      reviewed: fields={row['reviewed']['all_required_fields_present']}"
            f"  unresolved={len(row['reviewed']['unresolved_sections'])}"
            f"  publishable={row['reviewed']['publishable']}"
        )
        if row.get("live"):
            print(
                f"      detection: expected={det['expected']} gap={det['gap_detected']}"
                f" -> {det['label']}"
            )
            for finding in row["draft"]["noticeable_findings"][:3]:
                print(f"        - {finding[:96]}")
        for problem in row["model_parse_problems"][:3]:
            print(f"        ! {problem[:96]}")
    print("\n" + "-" * 74)
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print("-" * 74)
    print(
        "These are structural measurements only. They are not quality scores, "
        "not accuracy, and not a judgement of whether a budget is fair."
    )


#: Keys every scored artefact must expose, so a silent rubric regression fails.
DRAFT_KEYS = {
    "all_required_fields_present", "deliverables_count", "deliverables_specific",
    "criteria_count", "criteria_checkable", "objective_specific",
    "budget_preserved", "deadline_preserved", "noticeable_findings",
    "fairscope_signals", "clarity_checks_flagged", "clarity_checks_missing",
    "error_level_findings",
}
REVIEWED_KEYS = {
    "all_required_fields_present", "deliverables_count", "deliverables_specific",
    "criteria_count", "criteria_checkable", "unresolved_sections",
    "essential_gaps", "budget_preserved", "deadline_preserved", "publishable",
}


def _self_check_brief(case: dict[str, Any]) -> dict[str, Any]:
    """A deterministic stand-in brief, so the harness itself can be tested."""
    request = case["request"]
    return {
        "title": case["scenario"].replace("_", " ").title(),
        "objective": request["description"],
        "deliverables": ["One deliverable item"],
        "required_skills": ["Documentation"],
        "clarifying_questions": [],
        "acceptance_criteria": ["The deliverable is delivered and reviewed"],
        "assumptions": ["The business supplies the information"],
    }


def run_self_check() -> int:
    """Validate the harness with no model call at all.

    This checks the *machinery* - dataset loading, rubric shape, and that both
    artefacts are scored by the same code. It deliberately does **not** judge the
    detection criterion, because a hand-written stand-in brief says nothing
    about GPT-OSS.
    """
    cases = load_cases()
    problems: list[str] = []

    if len(cases) != 5:
        problems.append(f"expected 5 cases, found {len(cases)}")

    for case in cases:
        for field in ("id", "scenario", "request", "expect_detection", "expect_reason"):
            if field not in case:
                problems.append(f"{case.get('id')} missing {field}")
        request = case.get("request") or {}
        for field in ("project_name", "description", "outcome", "budget", "deadline"):
            if field not in request:
                problems.append(f"{case.get('id')} request missing {field}")

        row = evaluate_case(case, _self_check_brief(case))
        row["live"] = False
        row["source"] = "deterministic stand-in brief (no model call)"

        missing = DRAFT_KEYS - set(row["draft"])
        missing |= REVIEWED_KEYS - set(row["reviewed"])
        if missing:
            problems.append(f"{case['id']} rubric missing keys: {sorted(missing)}")
        if row["draft"]["artefact"] != "draft" or row["reviewed"]["artefact"] != "reviewed":
            problems.append(f"{case['id']} artefacts not distinguishable")

    if problems:
        print("SELF-CHECK FAILED")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("=" * 74)
    print("Gigsie FairScope evaluation - harness self-check (no model calls)")
    print("=" * 74)
    print(f"  dataset cases      : {len(cases)}")
    for case in cases:
        print(
            f"    - {case['id']:<26} expect_detection={case['expect_detection']}"
        )
    print("  rubric keys present: draft and reviewed both scored by the same code")
    print("  artefacts distinct: draft != reviewed, kept separate in all output")
    print()
    print(
        "Self-check only. No model was called, so NO detection, preservation, or "
        "completeness results are reported here - those need a live run:\n"
        "    python scripts/evaluate_fairscope.py --live"
    )
    return 0


def run_live(out_path: Path | None) -> int:
    results = []
    for case in load_cases():
        print(f"generating a real brief for {case['id']} ...", flush=True)
        result, problems = generate_brief_live(case["request"])
        brief = result.get("brief") or {}
        row = evaluate_case(case, brief, problems=problems)
        row["live"] = True
        row["source"] = "openai/gpt-oss-20b via Groq"
        # Recorded so the rubric can be re-applied later without another call.
        row["raw_brief"] = brief
        results.append(row)
    summary = summarise(results)
    print_report(results, summary)

    payload = {
        "model": "openai/gpt-oss-20b (Groq)",
        "case_count": len(results),
        "results": results,
        "summary": summary,
        "caveat": (
            "Automated structural measurements only. No quality, fairness, or "
            "accuracy score is claimed; those require human judgement."
        ),
        "replay_instructions": (
            "Each result carries the raw 'raw_brief' returned by the model, so "
            "the rubric can be re-applied without spending API credit. Re-score "
            "with evaluate_case(case, result['raw_brief'])."
        ),
    }
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nresults written to {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--live",
        action="store_true",
        help="call the real Groq model once per case (costs credits)",
    )
    group.add_argument(
        "--self-check",
        action="store_true",
        help="validate the harness with deterministic stand-in briefs (default)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="write results to this path as JSON",
    )
    args = parser.parse_args(argv)

    if args.live:
        return run_live(args.json)
    return run_self_check()


if __name__ == "__main__":
    raise SystemExit(main())
