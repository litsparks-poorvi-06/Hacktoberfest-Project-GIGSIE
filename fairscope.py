"""FairScope - deterministic scope review and the Gig Passport.

FairScope helps a small business turn a vague request into a clear, achievable
draft *before* it is published. The guiding rule is:

    The AI drafts. Python checks. The business decides.

Everything in this module is plain Python: no AI, no network, no guessing. The
model contributes *language* (a proposed brief, plus its own warnings and
questions). FairScope adds *deterministic* checks on top, keeps the two clearly
separated, and never invents a fact to make a brief look complete.

Honest limits (stated on purpose):

  * We do NOT judge whether a budget is fair - that would need market data we do
    not have. We only flag missing or inconsistent information.
  * There is NO numerical "feasibility score" and no promise that a task can be
    completed on time or within budget. A high deliverable count is a reason to
    review a task, not proof that it is impossible.

This module is intentionally free of Streamlit so it can be tested directly.
"""

from __future__ import annotations

import re
from typing import Any

import validation

# --- Clarity-check statuses ------------------------------------------------
STATUS_OK = "ok"
STATUS_NEEDS = "needs_clarification"
STATUS_MISSING = "missing"


# --- Scope strategies (canonical metadata) ---------------------------------
# The model-facing prompts for these live in gigsie_ai.py. Both modules read the
# same key list from here so they can never drift apart.
SCOPE_STRATEGIES: list[dict[str, str]] = [
    {
        "key": "budget_first",
        "label": "Budget-first",
        "blurb": (
            "Keep the stated budget and deadline. Reduce the work to a small, "
            "coherent set of deliverables that fit them, and state what is excluded."
        ),
    },
    {
        "key": "outcome_first",
        "label": "Outcome-first",
        "blurb": (
            "Keep the desired outcome. Show the work likely needed and flag any "
            "constraint that may need to change - nothing changes without your approval."
        ),
    },
    {
        "key": "milestone_first",
        "label": "Milestone-first",
        "blurb": (
            "Start with one independently verifiable first milestone, and state "
            "clearly what it includes and what stays outside it."
        ),
    },
]
SCOPE_STRATEGY_KEYS: list[str] = [item["key"] for item in SCOPE_STRATEGIES]
_SCOPE_STRATEGY_BY_KEY = {item["key"]: item for item in SCOPE_STRATEGIES}


def strategy_meta(key: Any) -> dict[str, str] | None:
    """Return the metadata for a strategy key, or None when it is unknown."""
    return _SCOPE_STRATEGY_BY_KEY.get(str(key or "").strip())


def strategy_label(key: Any) -> str:
    """Return a friendly label for a strategy key (or the key itself)."""
    meta = strategy_meta(key)
    if meta:
        return meta["label"]
    return str(key or "").strip() or "Unknown strategy"


# --- Language heuristics (documented, not magic) ---------------------------
# Words that usually signal a vague, hard-to-verify description. Used only to
# prompt a human to look again - never to score quality.
_VAGUE_WORDS = re.compile(
    r"\b(nice|good|great|engaging|appealing|attractive|professional|creative|"
    r"high[ -]?quality|effective|viral|impressive|modern|clean|better|improved?|"
    r"some|several|various|etc|and more|asap|things|stuff|beautiful|awesome|amazing)\b",
    re.IGNORECASE,
)

# Cues that a line can be checked objectively (a quantity or a concrete artefact).
_MEASURABLE_CUE = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|both|dozen|"
    r"at least|at most|no more than|exactly|within|each|per|checklist|list of|"
    r"ready[- ]to|ready[- ]to[- ]post|delivered|published|approved|must|includes?|included)\b",
    re.IGNORECASE,
)

# Broad, boundary-less requests ("manage all our marketing", "grow everything").
_BROAD = re.compile(
    r"\b(all|everything|any|every|entire|complete|full|ongoing|campaign|manage|"
    r"handle|grow|whole|end[- ]to[- ]end|comprehensive|from scratch|as needed)\b",
    re.IGNORECASE,
)

# Explicit scope boundaries / exclusions.
_BOUNDARY_CUE = re.compile(
    r"\b(only|exclude[sd]?|excluding|not included|not include|does not include|"
    r"outside (the )?scope|out of scope|limited to|no more than|first milestone|"
    r"scope boundary|boundaries|single)\b",
    re.IGNORECASE,
)

# Things a client often has to supply (assets, content, access).
_ASSET = re.compile(
    r"\b(photos?|images?|logo|brand(ing)?|video|videos|footage|content|copy|text|"
    r"account|access|login|credentials|files?|assets?|product (photos?|images?|info)|"
    r"screen ?shots?)\b",
    re.IGNORECASE,
)

# Mentions of revisions / changes without a stated limit.
_REVISION = re.compile(
    r"\b(revision|revisions|revise|edit|edits|changes?|feedback|iterate|iteration|"
    r"amend|tweak)\b",
    re.IGNORECASE,
)


# --- Small helpers ---------------------------------------------------------
def _finding(level: str, message: str) -> dict[str, str]:
    return {"level": level, "message": message, "source": "deterministic"}


def _check(
    key: str, label: str, status: str, detail: str, essential: bool
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "essential": essential,
    }


def _list(value: Any) -> list[str]:
    """Coerce a value into a clean list of strings. Never raises."""
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _is_vague(text: Any) -> bool:
    """True when a line is too short or only uses vague, unverifiable words."""
    value = str(text or "").strip()
    if len(value) < 6:
        return True
    if _VAGUE_WORDS.search(value) and not _MEASURABLE_CUE.search(value):
        return True
    return False


def _is_checkable(text: Any) -> bool:
    """True when a line contains something that can be checked objectively."""
    value = str(text or "").strip()
    return len(value) >= 8 and bool(_MEASURABLE_CUE.search(value))


def _is_specific(text: Any) -> bool:
    value = str(text or "").strip()
    return len(value) >= 15 and not _is_vague(value)


def _dedupe_findings(findings: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for finding in findings:
        message = finding.get("message", "")
        key = message.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(finding)
    return result


def _objective_of(brief: dict[str, Any]) -> str:
    return _text(brief.get("objective"), brief.get("project_objective"))


def _deliverables_of(brief: dict[str, Any]) -> list[str]:
    return _list(brief.get("deliverables")) or _list(brief.get("proposed_deliverables"))


# ===========================================================================
# A. Clarity check
# ===========================================================================
def clarity_checks(request: Any, brief: Any) -> dict[str, Any]:
    """Deterministically inspect a brief's clarity.

    Returns ``{"checks": [check, ...]}``. Each check is::

        {"key", "label", "status", "detail", "essential"}

    ``status`` is one of ``ok`` / ``needs_clarification`` / ``missing``. The
    ``essential`` flag marks information the business should resolve (or
    explicitly acknowledge) before publishing.
    """
    request = request if isinstance(request, dict) else {}
    brief = brief if isinstance(brief, dict) else {}

    objective = _objective_of(brief)
    deliverables = _deliverables_of(brief)
    criteria = _list(brief.get("acceptance_criteria"))
    skills = _list(brief.get("required_skills"))
    questions = _list(brief.get("clarifying_questions"))
    exclusions = _list(brief.get("exclusions"))
    assumptions = _list(brief.get("assumptions"))

    boundary_text = " ".join(
        [objective, " ".join(deliverables), " ".join(exclusions), " ".join(assumptions)]
    )

    checks: list[dict[str, Any]] = []

    # 1. A specific objective.
    if not objective:
        checks.append(
            _check("objective", "A specific objective", STATUS_MISSING,
                   "The brief has no objective yet.", True)
        )
    elif not _is_specific(objective):
        checks.append(
            _check("objective", "A specific objective", STATUS_NEEDS,
                   "The objective is vague. Say exactly what should change and for whom.", True)
        )
    else:
        checks.append(
            _check("objective", "A specific objective", STATUS_OK,
                   "The objective states a concrete goal.", True)
        )

    # 2. Concrete deliverables.
    if not deliverables:
        checks.append(
            _check("deliverables", "Concrete deliverables", STATUS_MISSING,
                   "No deliverables are listed, so there is nothing concrete to produce.", True)
        )
    else:
        vague = [item for item in deliverables if _is_vague(item)]
        if vague:
            checks.append(
                _check("deliverables", "Concrete deliverables", STATUS_NEEDS,
                       f"{len(vague)} deliverable(s) are vague. Name the exact item to be produced.", True)
            )
        else:
            checks.append(
                _check("deliverables", "Concrete deliverables", STATUS_OK,
                       f"{len(deliverables)} concrete deliverable(s) are listed.", True)
            )

    # 3. Measurable acceptance criteria.
    if not criteria:
        checks.append(
            _check("acceptance_criteria", "Measurable acceptance criteria", STATUS_MISSING,
                   "No acceptance criteria are listed, so 'done' is undefined.", True)
        )
    else:
        uncheckable = [item for item in criteria if not _is_checkable(item)]
        if uncheckable:
            checks.append(
                _check("acceptance_criteria", "Measurable acceptance criteria", STATUS_NEEDS,
                       f"{len(uncheckable)} acceptance criteria cannot be checked objectively.", True)
            )
        else:
            checks.append(
                _check("acceptance_criteria", "Measurable acceptance criteria", STATUS_OK,
                       "Each acceptance criterion can be checked.", True)
            )

    # 4. Relevant required skills.
    if not skills:
        checks.append(
            _check("required_skills", "Relevant required skills", STATUS_NEEDS,
                   "No skills are listed. Add the skills genuinely needed for this task.", True)
        )
    else:
        checks.append(
            _check("required_skills", "Relevant required skills", STATUS_OK,
                   f"{len(skills)} required skill(s) are listed.", True)
        )

    # 5. Clear scope boundaries.
    if _BOUNDARY_CUE.search(boundary_text):
        checks.append(
            _check("scope_boundaries", "Clear scope boundaries", STATUS_OK,
                   "The brief gives at least one boundary or exclusion.", False)
        )
    else:
        checks.append(
            _check("scope_boundaries", "Clear scope boundaries", STATUS_NEEDS,
                   "The brief does not say what is out of scope. State what this task does NOT include.", False)
        )

    # 6. Unanswered questions for the business to resolve.
    if questions:
        checks.append(
            _check("open_questions", "Unanswered questions", STATUS_NEEDS,
                   f"{len(questions)} open question(s) should be resolved before publishing.", False)
        )
    else:
        checks.append(
            _check("open_questions", "Unanswered questions", STATUS_OK,
                   "No open questions were flagged.", False)
        )

    return {"checks": checks}


# ===========================================================================
# B. Scope signals
# ===========================================================================
def scope_signals(request: Any, brief: Any) -> list[dict[str, str]]:
    """Deterministic warning signs that a scope may need review.

    All findings are ``source = "deterministic"``. They are prompts to look
    again - not proof of a problem and never a feasibility judgement.
    """
    request = request if isinstance(request, dict) else {}
    brief = brief if isinstance(brief, dict) else {}

    findings: list[dict[str, str]] = list(validation.validate_brief(request, brief))

    deliverables = _deliverables_of(brief)
    description = _text(request.get("description"), request.get("work_needed"))
    outcome = _text(request.get("outcome"), request.get("desired_outcome"))
    objective = _objective_of(brief)

    combined = " ".join([description, outcome, objective, " ".join(deliverables)])
    exclusions = _list(brief.get("exclusions"))
    assumptions = _list(brief.get("assumptions"))
    boundary_text = " ".join(
        [objective, " ".join(deliverables), " ".join(exclusions), " ".join(assumptions)]
    )

    days = validation.extract_days(request.get("deadline"))

    # Broad request without a boundary.
    if _BROAD.search(combined) and not _BOUNDARY_CUE.search(boundary_text):
        findings.append(
            _finding(
                "warning",
                "The request sounds broad (for example 'manage all' or 'everything'). "
                "Narrow it to one specific deliverable with clear boundaries before publishing.",
            )
        )

    # Many deliverables for one task (only when the deadline is not already very
    # short - validation.validate_brief already covers that case).
    if (
        len(deliverables) > validation.MAX_COMFORTABLE_DELIVERABLES
        and (days is None or days > validation.SHORT_DEADLINE_DAYS)
    ):
        findings.append(
            _finding(
                "warning",
                f"{len(deliverables)} deliverables are listed. Check that this is one small "
                "task and not several unrelated jobs bundled together.",
            )
        )

    # Missing assets / content / access.
    if _ASSET.search(combined) and not _list(brief.get("client_responsibilities")):
        findings.append(
            _finding(
                "warning",
                "The task appears to need assets, content, or account access. Confirm who "
                "provides each item; do not assume access, photos, or brand files will be granted.",
            )
        )

    # Unclear revision expectations.
    if _REVISION.search(combined) and not _list(brief.get("revision_expectations")):
        findings.append(
            _finding(
                "info",
                "The brief mentions edits or revisions but does not state how many are included. "
                "Agree the revision limit before publishing.",
            )
        )

    # Acceptance criteria that cannot be checked objectively.
    uncheckable = [item for item in _list(brief.get("acceptance_criteria")) if not _is_checkable(item)]
    if uncheckable:
        findings.append(
            _finding(
                "warning",
                f"{len(uncheckable)} acceptance criteria cannot be checked objectively. Rewrite "
                "them as something you can confirm (a count, a file, or a plain yes/no).",
            )
        )

    return _dedupe_findings(findings)


# ===========================================================================
# C. Recommended next action
# ===========================================================================
def recommended_action(
    clarity: dict[str, Any], signals: list[dict[str, str]]
) -> dict[str, Any]:
    """Turn the checks and signals into a short, actionable recommendation.

    No numeric feasibility score is produced and nothing is promised.
    """
    checks = clarity.get("checks", []) if isinstance(clarity, dict) else []
    essential = [
        check
        for check in checks
        if check.get("essential") and check.get("status") != STATUS_OK
    ]
    warnings = [f for f in signals if f.get("level") == "warning"]

    steps: list[str] = []
    if essential:
        summary = "Resolve the essential gaps below before publishing."
        steps.append(
            "Clarify: " + ", ".join(check["label"].lower() for check in essential) + "."
        )
    elif warnings:
        summary = "The brief is reviewable. Review the scope warnings before publishing."
    else:
        summary = "The brief looks reviewable. Confirm the details and publish when ready."

    for check in essential:
        steps.append(f"{check['label']}: {check['detail']}")

    if warnings:
        steps.append(f"Review {len(warnings)} scope warning(s) below before publishing.")
    if not steps:
        steps.append("No essential gaps were found. Review the Gig Passport and publish when ready.")

    return {"summary": summary, "steps": steps}


def analyze_brief(request: Any, brief: Any) -> dict[str, Any]:
    """Run the full FairScope review for a brief.

    Returns::

        {
          "clarity":       {"checks": [...]},        # deterministic
          "signals":       [finding, ...],           # deterministic
          "ai_suggestions": {"warnings", "assumptions", "questions"},  # from the model
          "next_action":   {"summary", "steps"},
        }

    Deterministic findings (``clarity``, ``signals``) are always kept separate
    from the model's own suggestions so the two are never confused.
    """
    brief = brief if isinstance(brief, dict) else {}
    clarity = clarity_checks(request, brief)
    signals = scope_signals(request, brief)
    ai_suggestions = {
        "warnings": _list(brief.get("warnings")),
        "assumptions": _list(brief.get("assumptions")),
        "questions": _list(brief.get("clarifying_questions")),
    }
    return {
        "clarity": clarity,
        "signals": signals,
        "ai_suggestions": ai_suggestions,
        "next_action": recommended_action(clarity, signals),
    }


# ===========================================================================
# Gig Passport
# ===========================================================================
# (key, label, kind, essential, clarify_when_empty)
#   kind = "list" | "text" | "budget"
#   essential = missing truth here is important enough to require a decision
#   clarify_when_empty = show a "Needs clarification" state when empty
PASSPORT_SECTIONS: list[tuple[str, str, str, bool, bool]] = [
    ("objective", "The objective", "text", True, True),
    ("deliverables", "Deliverables", "list", True, True),
    ("definition_of_done", "Definition of done", "list", True, True),
    ("included_work", "Included work", "list", False, True),
    ("exclusions", "Exclusions", "list", False, False),
    ("required_skills", "Required skills", "list", True, True),
    ("client_responsibilities", "Client responsibilities", "list", False, False),
    ("revision_expectations", "Revision expectations", "list", False, False),
    ("open_questions", "Open questions", "list", False, False),
    ("assumptions", "Assumptions", "list", False, False),
    ("budget", "Budget (INR)", "budget", False, True),
    ("deadline", "Deadline", "text", False, True),
    ("scope_warnings", "Scope warnings", "list", False, False),
]


def _budget_value(value: Any) -> float:
    if value in (None, "", 0, 0.0):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _needs_clarification(section: dict[str, Any]) -> bool:
    if not section.get("clarify_when_empty"):
        return False
    kind = section.get("kind")
    value = section.get("value")
    if kind == "list":
        return not value
    if kind == "budget":
        return value in (None, "", 0, 0.0)
    return not str(value or "").strip()


def build_passport(brief: Any, request: Any, analysis: Any = None) -> dict[str, Any]:
    """Build an editable Gig Passport from a brief and the original request.

    Missing information is NEVER invented: any section without data is marked
    ``needs_clarification`` so the owner can resolve or acknowledge it.
    """
    brief = brief if isinstance(brief, dict) else {}
    request = request if isinstance(request, dict) else {}

    if analysis is None:
        analysis = analyze_brief(request, brief)

    deliverables = _deliverables_of(brief)
    model_warnings = _list(brief.get("warnings"))
    signal_messages = [
        finding.get("message", "")
        for finding in analysis.get("signals", [])
        if isinstance(finding, dict)
    ]
    scope_warnings: list[str] = []
    for message in model_warnings + signal_messages:
        if message and message not in scope_warnings:
            scope_warnings.append(message)

    values: dict[str, Any] = {
        "objective": _objective_of(brief),
        "deliverables": deliverables,
        "definition_of_done": _list(brief.get("acceptance_criteria")),
        "included_work": list(deliverables),
        "exclusions": _list(brief.get("exclusions")),
        "required_skills": _list(brief.get("required_skills")),
        "client_responsibilities": _list(brief.get("client_responsibilities")),
        "revision_expectations": _list(brief.get("revision_expectations")),
        "open_questions": _list(brief.get("clarifying_questions")),
        "assumptions": _list(brief.get("assumptions")),
        "budget": _budget_value(request.get("budget", request.get("budget_inr"))),
        "deadline": _text(request.get("deadline")),
        "scope_warnings": scope_warnings,
    }

    sections: dict[str, dict[str, Any]] = {}
    for key, label, kind, essential, clarify_when_empty in PASSPORT_SECTIONS:
        section = {
            "label": label,
            "kind": kind,
            "essential": essential,
            "clarify_when_empty": clarify_when_empty,
            "value": values.get(key),
        }
        section["needs_clarification"] = _needs_clarification(section)
        sections[key] = section

    return {"sections": sections, "acknowledged": [], "stage": "draft"}


def update_passport_values(
    passport: dict[str, Any], values: dict[str, Any]
) -> dict[str, Any]:
    """Return a copy of ``passport`` with edited section values and recomputed flags."""
    if not isinstance(passport, dict):
        passport = build_passport({}, {})
    result = {
        "sections": {
            key: dict(section) for key, section in (passport.get("sections") or {}).items()
        },
        "acknowledged": list(passport.get("acknowledged") or []),
        "stage": passport.get("stage", "draft"),
    }
    for key, value in (values or {}).items():
        section = result["sections"].get(key)
        if section is None:
            continue
        section["value"] = value
        section["needs_clarification"] = _needs_clarification(section)
    return result


def acknowledge(passport: dict[str, Any], keys: Any) -> dict[str, Any]:
    """Return a copy of ``passport`` with additional sections acknowledged."""
    if not isinstance(passport, dict):
        return passport
    result = {
        "sections": {
            key: dict(section) for key, section in (passport.get("sections") or {}).items()
        },
        "acknowledged": list(passport.get("acknowledged") or []),
        "stage": passport.get("stage", "draft"),
    }
    for key in _list(keys):
        if key not in result["acknowledged"]:
            result["acknowledged"].append(key)
    return result


def passport_unresolved(passport: dict[str, Any]) -> list[str]:
    """Keys of sections that are marked ``needs_clarification``."""
    sections = passport.get("sections") if isinstance(passport, dict) else None
    if not isinstance(sections, dict):
        return []
    return [key for key, section in sections.items() if section.get("needs_clarification")]


def passport_essential_issues(passport: dict[str, Any]) -> list[str]:
    """Essential sections still unresolved and not explicitly acknowledged."""
    if not isinstance(passport, dict):
        return []
    sections = passport.get("sections") or {}
    acknowledged = set(_list(passport.get("acknowledged")))
    issues: list[str] = []
    for key, section in sections.items():
        if (
            section.get("essential")
            and section.get("needs_clarification")
            and key not in acknowledged
        ):
            issues.append(key)
    return issues


def passport_is_publishable(passport: dict[str, Any]) -> bool:
    """True when no essential section needs a decision before publishing."""
    return not passport_essential_issues(passport)


def passport_issue_labels(passport: dict[str, Any]) -> list[str]:
    """Friendly labels for the essential sections that still need a decision."""
    sections = passport.get("sections") if isinstance(passport, dict) else None
    if not isinstance(sections, dict):
        return []
    return [
        (sections.get(key) or {}).get("label", key)
        for key in passport_essential_issues(passport)
    ]


def passport_for_gig(gig: Any) -> dict[str, Any]:
    """Return a gig's saved passport, or build a read-only one from its brief.

    Gigs published before FairScope existed (and the labelled sample gigs) have
    no stored passport, so one is derived from their brief. The old field names
    (``project_objective`` / ``proposed_deliverables``) are read as well.
    """
    if not isinstance(gig, dict):
        return build_passport({}, {})

    stored = gig.get("passport")
    if isinstance(stored, dict) and stored.get("sections"):
        return stored

    brief = gig.get("brief") if isinstance(gig.get("brief"), dict) else {}
    flat_brief = {
        "objective": _objective_of(brief) or _text(gig.get("objective")),
        "deliverables": validation.get_deliverables(gig),
        "required_skills": validation.get_required_skills(gig),
        "acceptance_criteria": _list(brief.get("acceptance_criteria")),
        "clarifying_questions": _list(brief.get("clarifying_questions")),
        "assumptions": _list(brief.get("assumptions")),
        "warnings": _list(brief.get("warnings")) or _list(brief.get("scope_deadline_concerns")),
        "exclusions": _list(brief.get("exclusions")),
        "client_responsibilities": _list(brief.get("client_responsibilities")),
        "revision_expectations": _list(brief.get("revision_expectations")),
    }
    request = {
        "description": _text(gig.get("work_needed")),
        "outcome": _text(gig.get("desired_outcome")),
        "budget": gig.get("budget_inr"),
        "deadline": gig.get("deadline"),
    }
    return build_passport(flat_brief, request)
