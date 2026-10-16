"""Pure business logic for the Gigsie business workflow.

Everything UI-free lives here so it can be tested without Streamlit:

    * ``validate_form``      - check the request form (budget + deadline required),
    * ``build_gig_record``   - map the reviewed brief + request to the stored schema,
    * ``publish_gig``        - validate and save through storage.py,
    * ``publish_once``       - save at most once per draft, so Streamlit reruns
                               never publish duplicates.

app.py only does presentation and session state; the AI is only ever asked to
*draft*. This module is the deterministic gatekeeper for what gets stored.
"""

from __future__ import annotations

from typing import Any

import fairscope
import storage
import validation


class PublishError(Exception):
    """Raised when a gig cannot be published. The message is safe to show a user."""


def _error(message: str) -> dict[str, str]:
    return {"level": "error", "message": message, "source": "deterministic"}


# ---------------------------------------------------------------------------
# Text <-> list helpers (used by the editor and by the record builder)
# ---------------------------------------------------------------------------
def split_lines(text: Any) -> list[str]:
    """Split a textarea value into a clean list of non-empty lines."""
    if not isinstance(text, str):
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def join_lines(items: Any) -> str:
    """Render a list of items as newline-separated text for a textarea."""
    if not isinstance(items, (list, tuple)):
        return ""
    return "\n".join(str(item) for item in items)


def _clean_list(value: Any) -> list[str]:
    """Coerce a list (or newline-separated string) into a clean list of strings."""
    if isinstance(value, str):
        value = split_lines(value)
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


# ---------------------------------------------------------------------------
# Form validation (runs BEFORE any AI call)
# ---------------------------------------------------------------------------
def validate_form(values: Any) -> list[dict[str, str]]:
    """Validate the business request form.

    Description and outcome are required by validation.validate_request. On top
    of that, the Gigsie interface also requires a positive budget and a deadline.
    Returns a list of findings (``level`` = "error" blocks generation).
    """
    if not isinstance(values, dict):
        return [_error("The request could not be read.")]

    findings = list(validation.validate_request(values))

    budget = values.get("budget")
    if budget in (None, "", 0, 0.0):
        findings.append(_error("Please enter a budget in INR."))

    if not str(values.get("deadline") or "").strip():
        findings.append(_error("Please enter a deadline or an expected completion time."))

    return findings


# ---------------------------------------------------------------------------
# Turning a reviewed brief into a stored gig record
# ---------------------------------------------------------------------------
def build_gig_record(
    brief: Any, request: Any, passport: Any = None
) -> dict[str, Any]:
    """Map a reviewed brief + the original request into the stored gig schema.

    Mirrors ``data/sample_gigs.json``: top-level fields plus a nested ``brief``.
    The top-level ``required_skills`` lets the student-side matcher read skills
    directly, without depending on the brief's internal shape.

    A FairScope **Gig Passport** is stored alongside the gig so the student side
    can read the agreed scope. When ``passport`` is not given, one is derived
    deterministically from the brief - the owner's inputs are never invented.
    """
    brief = brief if isinstance(brief, dict) else {}
    request = request if isinstance(request, dict) else {}

    title = (
        str(brief.get("title") or "").strip()
        or str(request.get("project_name") or "").strip()
        or "Untitled gig"
    )
    objective = str(brief.get("objective") or "").strip()
    required_skills = _clean_list(brief.get("required_skills"))

    budget = request.get("budget")
    try:
        budget_inr = float(budget) if budget not in (None, "", 0, 0.0) else 0.0
    except (TypeError, ValueError):
        budget_inr = 0.0

    nested_brief: dict[str, Any] = {
        "objective": objective,
        "deliverables": _clean_list(brief.get("deliverables")),
        "required_skills": required_skills,
        "clarifying_questions": _clean_list(brief.get("clarifying_questions")),
        "acceptance_criteria": _clean_list(brief.get("acceptance_criteria")),
        "assumptions": _clean_list(brief.get("assumptions")),
        "warnings": _clean_list(brief.get("warnings")),
    }
    # FairScope's optional passport fields are carried through when present.
    for key in ("exclusions", "client_responsibilities", "revision_expectations"):
        if key in brief:
            nested_brief[key] = _clean_list(brief.get(key))

    if passport is None:
        passport = fairscope.build_passport(brief, request)

    return {
        "title": title,
        "business_name": str(request.get("project_name") or "").strip(),
        "work_needed": str(request.get("description") or "").strip(),
        "desired_outcome": str(request.get("outcome") or "").strip(),
        "budget_inr": budget_inr,
        "deadline": str(request.get("deadline") or "").strip(),
        "additional_context": str(request.get("extra_context") or "").strip(),
        "required_skills": required_skills,
        "brief": nested_brief,
        "passport": passport,
        "sample": False,
    }


def validate_for_publish(record: Any) -> list[dict[str, str]]:
    """Deterministic checks on the final (edited) record before saving."""
    return validation.validate_task(record)


def publish_gig(
    brief: Any, request: Any, data_dir: Any = None, passport: Any = None
) -> dict[str, Any]:
    """Validate and save one gig. Raises PublishError if it cannot be saved.

    Storage assigns the id, status ("open"), and timestamp via storage.add_gig,
    keeping the same conventions as the sample data.

    The Gig Passport is checked too: the gig cannot be published while an
    essential section still needs a decision that the owner has not resolved or
    explicitly acknowledged. Missing information is never invented to pass.
    """
    record = build_gig_record(brief, request, passport=passport)

    findings = validate_for_publish(record)
    if validation.has_errors(findings):
        messages = [f["message"] for f in findings if f["level"] == "error"]
        raise PublishError("This gig cannot be published yet: " + " ".join(messages))

    record_passport = record.get("passport")
    if not fairscope.passport_is_publishable(record_passport):
        labels = fairscope.passport_issue_labels(record_passport)
        raise PublishError(
            "The Gig Passport still needs a decision before publishing: "
            + ", ".join(labels)
            + ". Fill these in, or explicitly acknowledge them as not yet specified."
        )

    try:
        return storage.add_gig(record, data_dir=data_dir)
    except storage.StorageError as error:
        raise PublishError(f"The gig could not be saved: {error}") from error


def publish_once(
    state: dict[str, Any],
    draft_key: str,
    brief: Any,
    request: Any,
    data_dir: Any = None,
    passport: Any = None,
) -> dict[str, Any] | None:
    """Publish at most once per ``draft_key`` so reruns never create duplicates.

    ``state`` is a mutable mapping (for example ``st.session_state``). Returns the
    saved record, or ``None`` when this draft has already been published. If
    publishing fails, the state is not marked, so the owner may try again.
    """
    # ``state`` may be a plain dict or Streamlit's SessionState; both support
    # ``.get`` and item assignment, which is all this function needs.
    if state is None or not hasattr(state, "get"):
        raise PublishError("The publishing state could not be read.")
    if state.get("published_draft_key") == draft_key:
        return None

    record = publish_gig(brief, request, data_dir=data_dir, passport=passport)
    state["published_draft_key"] = draft_key
    return record
