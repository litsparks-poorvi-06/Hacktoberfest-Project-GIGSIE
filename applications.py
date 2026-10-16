"""Applications: a student's proposal for a gig, plus its status lifecycle.

The AI may *draft* a proposal, but this module is the deterministic gatekeeper:
it validates the proposal, prevents duplicate applications, and enforces a small,
explicit set of status transitions so the prototype can never show a
contradictory state (for example "accepted" -> "rejected").

Identity model (prototype only): applications are linked by ``profile_id`` and
``gig_id``. There are no real accounts, so "duplicate" means the same local
profile applying to the same gig twice.
"""

from __future__ import annotations

from typing import Any

from errors import WorkflowError
import storage
import validation

# --- Statuses --------------------------------------------------------------
STATUS_SUBMITTED = "submitted"
STATUS_SHORTLISTED = "shortlisted"
STATUS_INTERVIEW_REQUESTED = "interview_requested"
STATUS_INTERVIEW_CONFIRMED = "interview_confirmed"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"

STATUSES: tuple[str, ...] = (
    STATUS_SUBMITTED,
    STATUS_SHORTLISTED,
    STATUS_INTERVIEW_REQUESTED,
    STATUS_INTERVIEW_CONFIRMED,
    STATUS_ACCEPTED,
    STATUS_REJECTED,
)

# Statuses where an application is still "in play".
ACTIVE_STATUSES: tuple[str, ...] = (
    STATUS_SUBMITTED,
    STATUS_SHORTLISTED,
    STATUS_INTERVIEW_REQUESTED,
    STATUS_INTERVIEW_CONFIRMED,
)

TERMINAL_STATUSES: tuple[str, ...] = (STATUS_ACCEPTED, STATUS_REJECTED)

STATUS_LABELS: dict[str, str] = {
    STATUS_SUBMITTED: "Submitted",
    STATUS_SHORTLISTED: "Shortlisted",
    STATUS_INTERVIEW_REQUESTED: "Interview requested",
    STATUS_INTERVIEW_CONFIRMED: "Interview confirmed",
    STATUS_ACCEPTED: "Accepted",
    STATUS_REJECTED: "Rejected",
}

STATUS_MEANINGS: dict[str, str] = {
    STATUS_SUBMITTED: "Your proposal has been sent to the business.",
    STATUS_SHORTLISTED: "The business is interested and may request an interview.",
    STATUS_INTERVIEW_REQUESTED: "The business proposed an interview time.",
    STATUS_INTERVIEW_CONFIRMED: "An interview time is confirmed.",
    STATUS_ACCEPTED: "The business accepted this application.",
    STATUS_REJECTED: "The business decided not to continue with this application.",
}

# The only moves allowed between statuses. Anything else is a contradiction.
TRANSITIONS: dict[str, set[str]] = {
    STATUS_SUBMITTED: {STATUS_SHORTLISTED, STATUS_REJECTED, STATUS_INTERVIEW_REQUESTED},
    STATUS_SHORTLISTED: {STATUS_INTERVIEW_REQUESTED, STATUS_REJECTED, STATUS_ACCEPTED},
    STATUS_INTERVIEW_REQUESTED: {
        STATUS_INTERVIEW_CONFIRMED,
        STATUS_SHORTLISTED,
        STATUS_REJECTED,
    },
    STATUS_INTERVIEW_CONFIRMED: {STATUS_ACCEPTED, STATUS_REJECTED},
    STATUS_ACCEPTED: set(),
    STATUS_REJECTED: set(),
}

MIN_PROPOSAL_CHARS = 40
MAX_PROPOSAL_CHARS = 2000


def can_transition(current: Any, new: Any) -> bool:
    """True when moving from ``current`` to ``new`` is an allowed transition."""
    if current == new:
        return True
    return new in TRANSITIONS.get(str(current), set())


def validate_proposal(text: Any) -> list[dict[str, str]]:
    """Validate the student's proposal text."""
    findings: list[dict[str, str]] = []
    proposal = text.strip() if isinstance(text, str) else ""
    if not proposal:
        findings.append({"level": "error", "message": "Write a short proposal before submitting."})
    elif len(proposal) < MIN_PROPOSAL_CHARS:
        findings.append(
            {
                "level": "error",
                "message": (
                    f"Your proposal is very short. Add a little more detail "
                    f"(at least {MIN_PROPOSAL_CHARS} characters)."
                ),
            }
        )
    elif len(proposal) > MAX_PROPOSAL_CHARS:
        findings.append(
            {
                "level": "warning",
                "message": f"Your proposal is quite long ({len(proposal)} characters). Shorter is easier to review.",
            }
        )
    return findings


def _index_of(applications: list[dict[str, Any]], application_id: str) -> int | None:
    for index, application in enumerate(applications):
        if application.get("id") == application_id:
            return index
    return None


def find_duplicate(profile_id: Any, gig_id: Any, data_dir: Any = None) -> dict[str, Any] | None:
    """Return an existing application by this profile for this gig, if any."""
    if not profile_id or not gig_id:
        return None
    for application in storage.load_applications(data_dir):
        if application.get("profile_id") == profile_id and application.get("gig_id") == gig_id:
            return application
    return None


def submit_application(
    profile: Any,
    gig: Any,
    proposal: Any,
    ai_assisted: bool = False,
    data_dir: Any = None,
) -> dict[str, Any]:
    """Validate and save a student's application. Raises ``WorkflowError``."""
    if not isinstance(profile, dict) or not profile.get("id"):
        raise WorkflowError("Select or create a student profile before applying.")
    if not isinstance(gig, dict) or not gig.get("id"):
        raise WorkflowError("This gig could not be read, so it cannot be applied for.")

    findings = validate_proposal(proposal)
    if validation.has_errors(findings):
        messages = [f["message"] for f in findings if f["level"] == "error"]
        raise WorkflowError(" ".join(messages))

    duplicate = find_duplicate(profile.get("id"), gig.get("id"), data_dir)
    if duplicate is not None:
        raise WorkflowError(
            "You have already applied for this gig with this profile "
            f"(application {duplicate.get('id')})."
        )

    now = storage.now_iso()
    record = {
        "gig_id": gig.get("id"),
        "gig_title": gig.get("title") or "Untitled gig",
        "profile_id": profile.get("id"),
        "student_name": profile.get("display_name") or "Unnamed student",
        "proposal": proposal.strip() if isinstance(proposal, str) else "",
        "ai_assisted": bool(ai_assisted),
        "status": STATUS_SUBMITTED,
        "identity_model": "local_prototype_profile",
        "created_at": now,
        "updated_at": now,
    }
    return storage.save_application(record, data_dir)


def get_application(application_id: Any, data_dir: Any = None) -> dict[str, Any] | None:
    for application in storage.load_applications(data_dir):
        if application.get("id") == application_id:
            return application
    return None


def all_applications(data_dir: Any = None) -> list[dict[str, Any]]:
    return storage.load_applications(data_dir)


def applications_for_profile(profile_id: Any, data_dir: Any = None) -> list[dict[str, Any]]:
    return [
        application
        for application in storage.load_applications(data_dir)
        if application.get("profile_id") == profile_id
    ]


def applications_for_gig(gig_id: Any, data_dir: Any = None) -> list[dict[str, Any]]:
    return [
        application
        for application in storage.load_applications(data_dir)
        if application.get("gig_id") == gig_id
    ]


def update_status(
    application_id: Any, new_status: Any, data_dir: Any = None
) -> dict[str, Any]:
    """Move an application to ``new_status``, enforcing the transition rules.

    Raises ``WorkflowError`` when the application is missing, the status is
    unknown, or the move would be contradictory. Re-applying the current status
    is a safe no-op (so Streamlit reruns never break anything).
    """
    if new_status not in STATUSES:
        raise WorkflowError(f"'{new_status}' is not a valid application status.")

    applications = storage.load_applications(data_dir)
    index = _index_of(applications, application_id)
    if index is None:
        raise WorkflowError("That application could not be found.")

    record = applications[index]
    current = record.get("status")

    if current == new_status:
        return record
    if not can_transition(current, new_status):
        raise WorkflowError(
            f"An application that is '{STATUS_LABELS.get(current, current)}' cannot be "
            f"changed to '{STATUS_LABELS.get(new_status, new_status)}'."
        )

    updated = dict(record)
    updated["status"] = new_status
    updated["updated_at"] = storage.now_iso()
    applications[index] = updated
    storage.save_applications(applications, data_dir)
    return updated


def save_application_record(record: dict[str, Any], data_dir: Any = None) -> dict[str, Any]:
    """Overwrite one stored application in place (used by the interview flow)."""
    applications = storage.load_applications(data_dir)
    index = _index_of(applications, record.get("id"))
    if index is None:
        raise WorkflowError("That application could not be found.")
    applications[index] = record
    storage.save_applications(applications, data_dir)
    return record
