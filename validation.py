"""Deterministic validation checks for Gigsie.

Everything here is plain Python: no AI, no network, no guessing.
These findings are explainable rules and are always kept separate from the
model's suggestions. Each finding is a dict:

    {"level": "error" | "warning" | "info",
     "message": "...",
     "source": "deterministic"}

We deliberately do NOT judge whether a budget is fair - that would require
market data we do not have. We only flag missing or inconsistent information.
"""

from __future__ import annotations

import re
from typing import Any

# --- Heuristic thresholds (documented, not magic numbers) -------------------
# A beginner freelancer can usually focus on a small number of deliverables.
# More than this within a very short deadline is worth flagging. This is a
# heuristic prompt for a human, not a rule about productivity.
MAX_COMFORTABLE_DELIVERABLES = 3

# Anything this short counts as a "very short" deadline for the check above.
SHORT_DEADLINE_DAYS = 2

# More skills than this is hard for a single beginner to cover.
BUSY_SKILLS_THRESHOLD = 5


def _finding(level: str, message: str) -> dict[str, str]:
    return {"level": level, "message": message, "source": "deterministic"}


def extract_days(value: Any) -> int | None:
    """Read a rough number of days from free text.

    Handles "2 days", "48 hours", "1 week", or a bare number. It is a simple
    heuristic: if it cannot find anything sensible it returns None, and callers
    should skip time-based checks rather than guess.
    """
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value or "").lower()

    day_match = re.search(r"(\d+)\s*day", text)
    if day_match:
        return int(day_match.group(1))

    hour_match = re.search(r"(\d+)\s*hour", text)
    if hour_match:
        hours = int(hour_match.group(1))
        return max(1, round(hours / 24))

    week_match = re.search(r"(\d+)\s*week", text)
    if week_match:
        return int(week_match.group(1)) * 7

    any_number = re.search(r"\d+", text)
    if any_number:
        return int(any_number.group())

    return None


def validate_request(request: dict[str, Any]) -> list[dict[str, str]]:
    """Check the form BEFORE any API call. Returns findings (errors block generation).

    Only the work description and the desired outcome are required. Business name,
    budget, deadline, and additional information are optional.
    """
    findings: list[dict[str, str]] = []

    if not str(request.get("description") or "").strip():
        findings.append(_finding("error", "Please describe the work that needs to be done."))

    if not str(request.get("outcome") or "").strip():
        findings.append(_finding("error", "Please describe the outcome the business wants."))

    # Budget is optional. If a value is given, it just has to be a sensible number.
    budget = request.get("budget")
    if budget not in (None, "", 0, 0.0):
        try:
            amount = float(budget)
        except (TypeError, ValueError):
            findings.append(_finding("error", "The budget must be a number in INR."))
        else:
            if amount < 0:
                findings.append(_finding("error", "The budget cannot be negative."))

    return findings


def validate_brief(
    request: dict[str, Any], brief: dict[str, Any]
) -> list[dict[str, str]]:
    """Check the generated brief against the original request.

    These are all deterministic comparisons - no model judgement involved.
    Reads either brief shape: the AI layer's keys (objective / deliverables)
    or the older sample-data keys (project_objective / proposed_deliverables).
    """
    if not isinstance(brief, dict):
        return [_finding("error", "The brief could not be read.")]

    findings: list[dict[str, str]] = []

    deliverables = _as_string_list(brief.get("deliverables")) or _as_string_list(
        brief.get("proposed_deliverables")
    )
    skills = _as_string_list(brief.get("required_skills"))
    objective = _first_text(brief, ["objective", "project_objective"])
    days = extract_days(request.get("deadline"))

    if not deliverables:
        findings.append(
            _finding("warning", "The brief lists no deliverables, so there is nothing concrete to review.")
        )

    if not objective:
        findings.append(_finding("warning", "The project objective is empty."))

    # Deliverables vs. a short deadline.
    if deliverables and days is None:
        findings.append(
            _finding(
                "info",
                "No clear number of days could be read from the deadline, so scope vs. time was not checked.",
            )
        )
    elif deliverables and days is not None and days <= SHORT_DEADLINE_DAYS and len(deliverables) > MAX_COMFORTABLE_DELIVERABLES:
        findings.append(
            _finding(
                "warning",
                f"{len(deliverables)} deliverables were proposed for a {days}-day deadline. "
                "Consider reducing the scope or extending the deadline.",
            )
        )

    # Budget presence vs. proposed work.
    budget = request.get("budget")
    if deliverables and budget in (None, "", 0, 0.0):
        findings.append(
            _finding("warning", "Deliverables were proposed, but no budget was given.")
        )

    # Many skills for one beginner.
    if len(skills) > BUSY_SKILLS_THRESHOLD:
        findings.append(
            _finding(
                "info",
                f"{len(skills)} skills are required, which may be hard for one beginner to cover.",
            )
        )

    return findings


def has_errors(findings: list[dict[str, str]]) -> bool:
    """True if any finding is a blocking error."""
    return any(finding.get("level") == "error" for finding in findings)


# ===========================================================================
# Stage 2: task/profile validation and transparent skill matching
# ===========================================================================
#
# Note on field names. The project currently uses two shapes for the same idea:
#   * The business form / gigsie_ai.py : description, outcome, budget, deadline
#   * A published gig (sample data)    : work_needed, desired_outcome, budget_inr,
#                                        deadline, plus a nested "brief" holding
#                                        proposed_deliverables / required_skills.
# The helpers below read either shape, so nothing existing breaks. No shared
# interface was changed.

# The experience levels we recognise. Anything else is a warning, never an error.
EXPERIENCE_LEVELS = {"beginner", "intermediate", "advanced"}

# Shown alongside every match result. Matching is advice, not a verdict.
MATCH_DISCLAIMER = (
    "A listed skill is a self-reported skill, not proof of competence. "
    "This match is a suggestion, not a hiring decision."
)


# --- Reading values safely ------------------------------------------------
def _first_text(data: dict[str, Any], keys: list[str]) -> str:
    """Return the first non-empty text value among several possible key names."""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _as_string_list(value: Any) -> list[str]:
    """Coerce a value into a clean list of strings. Never raises.

    Strings are split on commas/newlines/semicolons, lists are cleaned, and
    anything unexpected becomes an empty list.
    """
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,\n;]", value)
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    items.append(item.strip())
            elif isinstance(item, (int, float)) and not isinstance(item, bool):
                items.append(str(item))
        return items
    return []


def _brief_of(gig: dict[str, Any]) -> dict[str, Any]:
    """Return the nested 'brief' dict if present, else an empty dict."""
    brief = gig.get("brief")
    return brief if isinstance(brief, dict) else {}


def get_required_skills(gig: Any) -> list[str]:
    """Read a gig's required skills from the top level or the nested brief."""
    if not isinstance(gig, dict):
        return []
    return _as_string_list(gig.get("required_skills")) or _as_string_list(
        _brief_of(gig).get("required_skills")
    )


def get_deliverables(gig: Any) -> list[str]:
    """Read a gig's deliverables from the top level or the nested brief."""
    if not isinstance(gig, dict):
        return []
    return (
        _as_string_list(gig.get("proposed_deliverables"))
        or _as_string_list(gig.get("deliverables"))
        or _as_string_list(_brief_of(gig).get("proposed_deliverables"))
        or _as_string_list(_brief_of(gig).get("deliverables"))
    )


def normalize_skill(skill: Any) -> str:
    """Lower-case, trim, and collapse whitespace so ' Canva ' equals 'canva'."""
    if not isinstance(skill, str):
        return ""
    return re.sub(r"\s+", " ", skill.strip().lower())


def normalize_skills(skills: Any) -> list[str]:
    """Return unique normalized skills, keeping first-seen order."""
    result: list[str] = []
    for skill in _as_string_list(skills):
        normalized = normalize_skill(skill)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _dedupe_display(skills: Any) -> list[str]:
    """Unique skills in their original wording (case-insensitive de-duplication)."""
    result: list[str] = []
    seen: set[str] = set()
    for skill in _as_string_list(skills):
        key = normalize_skill(skill)
        if key and key not in seen:
            seen.add(key)
            result.append(skill)
    return result


def parse_duration_days(value: Any) -> int | None:
    """Read days ONLY from explicit day/week wording (e.g. '2 days', '1 week').

    Unlike extract_days, this never grabs a bare number, so '10 hrs/week' or a
    date like '15 Oct 2026' safely returns None instead of a misleading value.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value) if value > 0 else None
    text = str(value or "").lower()
    day_match = re.search(r"(\d+)\s*day", text)
    if day_match:
        return int(day_match.group(1))
    week_match = re.search(r"(\d+)\s*week", text)
    if week_match:
        return int(week_match.group(1)) * 7
    return None


# --- Validating a business task / gig -------------------------------------
def validate_task(task: Any) -> list[dict[str, str]]:
    """Validate a business task (or a published gig).

    Required: a work description, a desired outcome, and at least one deliverable.
    Optional (validated only if supplied): title, budget, deadline.
    Budget and deadline stay optional, matching the existing product design.
    """
    if not isinstance(task, dict):
        return [_finding("error", "The task details could not be read.")]

    findings: list[dict[str, str]] = []

    title = _first_text(task, ["title", "project_objective"])
    description = _first_text(task, ["work_needed", "description"])
    outcome = _first_text(task, ["desired_outcome", "outcome"])
    deliverables = get_deliverables(task)

    if not description:
        findings.append(_finding("error", "Describe the work that needs to be done."))
    if not outcome:
        findings.append(_finding("error", "Describe the outcome the business wants."))
    if not deliverables:
        findings.append(
            _finding("error", "Add at least one deliverable so students know what to produce.")
        )
    if not title:
        findings.append(_finding("warning", "Add a short title so students can scan the gig board."))

    # Budget is optional. If present it must be a sensible number.
    budget = task.get("budget_inr", task.get("budget"))
    if budget not in (None, "", 0, 0.0):
        if isinstance(budget, bool):
            findings.append(_finding("error", "The budget must be a number in INR."))
        else:
            try:
                amount = float(budget)
            except (TypeError, ValueError):
                findings.append(_finding("error", "The budget must be a number in INR."))
            else:
                if amount < 0:
                    findings.append(_finding("error", "The budget cannot be negative."))

    # Deadline is optional, but if supplied it should be usable text.
    deadline = task.get("deadline")
    if deadline is not None and not isinstance(deadline, (str, int, float)):
        findings.append(
            _finding("warning", "The deadline should be text such as '2 days' or a date.")
        )

    return findings


# A published gig is just a task, so the same function is available under this name.
validate_gig = validate_task


# --- Validating a student profile -----------------------------------------
def _looks_like_link(text: str) -> bool:
    return bool(re.match(r"^(https?://)?[\w.-]+\.[a-zA-Z]{2,}(\S*)$", text.strip()))


def validate_profile(profile: Any) -> list[dict[str, str]]:
    """Validate a student profile.

    Required: a display name and at least one skill (beginners can list any
    skill, and no portfolio or professional experience is required).
    Optional: experience level, bio, availability, portfolio links.
    """
    if not isinstance(profile, dict):
        return [_finding("error", "The profile could not be read.")]

    findings: list[dict[str, str]] = []

    name = _first_text(profile, ["display_name", "name"])
    if not name:
        findings.append(_finding("error", "Add a display name so businesses know who applied."))

    skills = _as_string_list(profile.get("skills"))
    if not skills:
        findings.append(_finding("error", "List at least one skill so gigs can be matched to you."))

    level = profile.get("experience_level")
    if isinstance(level, str) and level.strip():
        if normalize_skill(level) not in EXPERIENCE_LEVELS:
            findings.append(
                _finding("warning", "Experience level should be Beginner, Intermediate, or Advanced.")
            )
    elif level not in (None, ""):
        findings.append(_finding("warning", "Experience level should be text such as 'Beginner'."))

    links = _as_string_list(profile.get("portfolio_links"))
    invalid = [link for link in links if not _looks_like_link(link)]
    if invalid:
        findings.append(
            _finding("warning", f"{len(invalid)} portfolio link(s) do not look like a valid web address.")
        )

    return findings


# --- Transparent skill matching -------------------------------------------
def _skills_match(required_norm: str, student_norms: set[str]) -> str | None:
    """How a required skill matches a student's skills: 'exact', 'phrase', or None.

    Rules (deliberately narrow to avoid vague keyword overlap):
      * 'exact'  - the normalized skill is identical.
      * 'phrase' - the shorter phrase's words are all present in the longer phrase,
                   and the shorter phrase has at least two words
                   (e.g. 'graphic design' inside 'graphic design tools').
      * Single generic words are NEVER treated as a match.
    """
    if not required_norm:
        return None
    if required_norm in student_norms:
        return "exact"

    required_words = required_norm.split()
    for candidate in student_norms:
        shorter, longer = sorted((required_words, candidate.split()), key=len)
        if len(shorter) >= 2 and set(shorter) <= set(longer):
            return "phrase"
    return None


def match_gig_to_skills(gig: Any, profile: Any) -> dict[str, Any]:
    """Compare a gig's required skills with a student's self-reported skills.

    Returns a structured, explainable result and never raises on odd input:
        {
          "score": int | None,      # 0-100, or None when it cannot be calculated
          "matched": [str],         # required skills the profile lists
          "missing": [str],         # required skills the profile does not list
          "reasons": [str],         # plain-English explanation
          "availability_note": str, # availability comparison, if possible
          "summary": str,           # one-line headline
          "disclaimer": str,        # reminder that skills are self-reported
        }

    Scoring: matched required skills / total required skills * 100. If the gig
    lists no skills, or the profile lists none, the score is None (not 0), so we
    never imply a poor match from missing information.
    """
    if not isinstance(gig, dict):
        gig = {}
    if not isinstance(profile, dict):
        profile = {}

    required = _dedupe_display(get_required_skills(gig))
    student = _dedupe_display(profile.get("skills"))
    student_norms = {normalize_skill(skill) for skill in student}
    student_norms.discard("")

    matched: list[str] = []
    missing: list[str] = []
    phrase_count = 0
    for skill in required:
        how = _skills_match(normalize_skill(skill), student_norms)
        if how is None:
            missing.append(skill)
        else:
            matched.append(skill)
            if how == "phrase":
                phrase_count += 1

    reasons: list[str] = []
    score: int | None
    if not required:
        score = None
        reasons.append("This gig does not list specific skills, so a match score cannot be calculated.")
    elif not student_norms:
        score = None
        reasons.append("Your profile does not list any skills yet, so a match score cannot be calculated.")
    else:
        score = round(100 * len(matched) / len(required))
        reasons.append(f"{len(matched)} of {len(required)} required skills appear in your profile.")
        if matched:
            reasons.append("Matched: " + ", ".join(matched) + ".")
        if missing:
            reasons.append("Not listed in your profile: " + ", ".join(missing) + ".")
        else:
            reasons.append("You list every required skill.")
        if phrase_count:
            reasons.append("Some matches are approximate (similar wording), so double-check the details.")

    available_days = parse_duration_days(profile.get("available_time"))
    deadline_days = parse_duration_days(gig.get("deadline"))
    if available_days is None or deadline_days is None:
        availability_note = (
            "Availability could not be checked (availability or deadline is missing "
            "or not in a comparable form)."
        )
    elif available_days < deadline_days:
        availability_note = (
            f"Your stated availability is about {available_days} day(s), which is shorter than "
            f"the {deadline_days}-day deadline. Check that you can still deliver in time."
        )
    else:
        availability_note = (
            f"No availability mismatch detected (about {available_days} day(s) available "
            f"vs a {deadline_days}-day deadline)."
        )

    summary = reasons[0] if score is None else (
        f"{score}% skill match ({len(matched)} of {len(required)} required skills listed)."
    )

    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "reasons": reasons,
        "availability_note": availability_note,
        "summary": summary,
        "disclaimer": MATCH_DISCLAIMER,
    }


def rank_gigs(gigs: Any, profile: Any) -> list[dict[str, Any]]:
    """Return [{"gig": ..., "match": ...}] sorted by match score, best first.

    Gigs without a meaningful score are placed last, keeping their original order.
    """
    if not isinstance(gigs, list):
        return []
    items = [
        {"gig": gig, "match": match_gig_to_skills(gig, profile)}
        for gig in gigs
        if isinstance(gig, dict)
    ]
    items.sort(
        key=lambda item: (item["match"]["score"] is not None, item["match"]["score"] or 0),
        reverse=True,
    )
    return items
