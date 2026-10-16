"""Interview coordination: status and scheduling details only.

What an interview means here: the two parties agree on a time (and optionally a
meeting link) through the app's *stored status*. Gigsie does **not** host video
calls, send emails or calendar invites, or provide real-time messaging.

Roles are passed explicitly (``actor="student"`` / ``actor="business"``) because
this prototype has no authentication - the UI only shows the buttons that make
sense for the section you are in.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import applications
from errors import WorkflowError
import storage
import validation

# --- Interview statuses ----------------------------------------------------
# The lifecycle: the business proposes a time (requested); the student accepts
# (accepted), proposes another time (alternative_proposed), or declines
# (declined); the business confirms the agreed time (confirmed).
INTERVIEW_REQUESTED = "requested"
INTERVIEW_ACCEPTED = "accepted"
INTERVIEW_ALTERNATIVE_PROPOSED = "alternative_proposed"
INTERVIEW_CONFIRMED = "confirmed"
INTERVIEW_DECLINED = "declined"

INTERVIEW_STATUSES: tuple[str, ...] = (
    INTERVIEW_REQUESTED,
    INTERVIEW_ACCEPTED,
    INTERVIEW_ALTERNATIVE_PROPOSED,
    INTERVIEW_CONFIRMED,
    INTERVIEW_DECLINED,
)

INTERVIEW_STATUS_LABELS: dict[str, str] = {
    INTERVIEW_REQUESTED: "Requested",
    INTERVIEW_ACCEPTED: "Accepted - awaiting confirmation",
    INTERVIEW_ALTERNATIVE_PROPOSED: "Alternative time proposed",
    INTERVIEW_CONFIRMED: "Confirmed",
    INTERVIEW_DECLINED: "Declined",
}

# An interview in one of these states is still open (not a duplicate).
OPEN_INTERVIEW_STATUSES: tuple[str, ...] = (
    INTERVIEW_REQUESTED,
    INTERVIEW_ACCEPTED,
    INTERVIEW_ALTERNATIVE_PROPOSED,
    INTERVIEW_CONFIRMED,
)

# Open states where the business still has something to do.
PENDING_BUSINESS_STATUSES: tuple[str, ...] = (
    INTERVIEW_REQUESTED,
    INTERVIEW_ACCEPTED,
    INTERVIEW_ALTERNATIVE_PROPOSED,
)

# Actions the student may take, and the statuses they are valid in. A student can
# only answer a fresh request; once they have accepted, they wait for the
# business rather than answering again.
STUDENT_ACTIONS: dict[str, set[str]] = {
    "accept": {INTERVIEW_REQUESTED},
    "decline": {INTERVIEW_REQUESTED},
    "propose_alternative": {INTERVIEW_REQUESTED},
}

# Actions the business may take. "confirm"/"decline" apply once the student has
# accepted or proposed another time; "cancel" also covers a request the student
# has not answered yet. The *_alternative names are kept as aliases.
BUSINESS_ACTIONS: dict[str, set[str]] = {
    "confirm": {INTERVIEW_ACCEPTED, INTERVIEW_ALTERNATIVE_PROPOSED},
    "decline": {INTERVIEW_ACCEPTED, INTERVIEW_ALTERNATIVE_PROPOSED},
    "cancel": {INTERVIEW_REQUESTED, INTERVIEW_ACCEPTED, INTERVIEW_ALTERNATIVE_PROPOSED},
    "accept_alternative": {INTERVIEW_ALTERNATIVE_PROPOSED},
    "decline_alternative": {INTERVIEW_ALTERNATIVE_PROPOSED},
}

# Business actions that finalise the agreed time.
_CONFIRMING_ACTIONS: frozenset[str] = frozenset({"confirm", "accept_alternative"})

DATETIME_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d %b %Y %H:%M",
    "%d %b %Y",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
)

_URL_RE = re.compile(r"^https?://[\w.-]+\.[a-zA-Z]{2,}(\S*)$")


def _to_local_naive(value: datetime) -> datetime:
    """Convert a possibly timezone-aware datetime into local naive time.

    Kept small so every comparison in this module uses one wall-clock convention.
    """
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def local_timezone_label() -> str:
    """A short label for this device's local timezone, e.g. ``IST (UTC+05:30)``.

    The prototype stores times as plain local wall-clock text, so the interface
    must say which timezone that is. This never guesses or converts a user's time
    to another zone.
    """
    now = datetime.now().astimezone()
    name = now.tzname() or "local time"
    offset = now.utcoffset()
    if offset is None:
        return name
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"{name} (UTC{sign}{hours:02d}:{minutes:02d})"


def _now() -> str:
    return storage.now_iso()


# ---------------------------------------------------------------------------
# Validating dates and links
# ---------------------------------------------------------------------------
def parse_datetime(value: Any) -> datetime | None:
    """Parse a date/time from a few friendly formats. Returns None if unusable."""
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def normalize_datetime(value: Any) -> str:
    """Return a consistent ``YYYY-MM-DD HH:MM`` local string, or the original text."""
    parsed = parse_datetime(value)
    if parsed is None:
        return str(value or "").strip()
    return _to_local_naive(parsed).strftime("%Y-%m-%d %H:%M")


def validate_datetime(value: Any, label: str = "Interview date and time") -> list[dict[str, str]]:
    """Validate a proposed interview date/time.

    A date in the past is an *error*: the prototype must never let either side
    save a time that has already happened.
    """
    if not str(value or "").strip():
        return [{"level": "error", "message": f"{label} is required (for example 2026-10-20 15:00)."}]
    parsed = parse_datetime(value)
    if parsed is None:
        return [
            {
                "level": "error",
                "message": (
                    f"{label} could not be understood. Use a format like 2026-10-20 15:00."
                ),
            }
        ]
    if _to_local_naive(parsed) < datetime.now():
        return [
            {
                "level": "error",
                "message": f"{label} is in the past. Choose a future date and time.",
            }
        ]
    return []


def validate_meeting_url(value: Any) -> list[dict[str, str]]:
    """Validate an optional meeting link (must be a http/https URL if given)."""
    text = str(value or "").strip()
    if not text:
        return []
    if not _URL_RE.match(text):
        return [
            {
                "level": "error",
                "message": "The meeting link must be a full web address, e.g. https://meet.example.com/abc.",
            }
        ]
    return []


def validate_interview_request(requested_datetime: Any, meeting_url: Any = "") -> list[dict[str, str]]:
    findings = validate_datetime(requested_datetime)
    findings.extend(validate_meeting_url(meeting_url))
    return findings


# ---------------------------------------------------------------------------
# Reading and writing
# ---------------------------------------------------------------------------
def _index_of(interviews: list[dict[str, Any]], interview_id: str) -> int | None:
    for index, interview in enumerate(interviews):
        if interview.get("id") == interview_id:
            return index
    return None


def get_interview(interview_id: Any, data_dir: Any = None) -> dict[str, Any] | None:
    for interview in storage.load_interviews(data_dir):
        if interview.get("id") == interview_id:
            return interview
    return None


def interviews_for_application(application_id: Any, data_dir: Any = None) -> list[dict[str, Any]]:
    return [
        interview
        for interview in storage.load_interviews(data_dir)
        if interview.get("application_id") == application_id
    ]


def active_interview_for_application(
    application_id: Any, data_dir: Any = None
) -> dict[str, Any] | None:
    """Return an open interview for this application, if one exists."""
    for interview in interviews_for_application(application_id, data_dir):
        if interview.get("status") in OPEN_INTERVIEW_STATUSES:
            return interview
    return None


def interviews_for_profile(profile_id: Any, data_dir: Any = None) -> list[dict[str, Any]]:
    return [
        interview
        for interview in storage.load_interviews(data_dir)
        if interview.get("profile_id") == profile_id
    ]


def interviews_for_gigs(gig_ids: Any, data_dir: Any = None) -> list[dict[str, Any]]:
    wanted = set(gig_ids or [])
    return [
        interview
        for interview in storage.load_interviews(data_dir)
        if interview.get("gig_id") in wanted
    ]


def _save(interview: dict[str, Any], data_dir: Any) -> dict[str, Any]:
    interviews = storage.load_interviews(data_dir)
    index = _index_of(interviews, interview.get("id"))
    if index is None:
        interviews.append(interview)
    else:
        interviews[index] = interview
    storage.save_interviews(interviews, data_dir)
    return interview


def _log(interview: dict[str, Any], actor: str, action: str, note: str = "") -> None:
    interview.setdefault("history", []).append(
        {"at": _now(), "actor": actor, "action": action, "note": note}
    )


def _new_id() -> str:
    from uuid import uuid4

    return f"i_{uuid4().hex[:8]}"


def _guard_application(interview: dict[str, Any], data_dir: Any = None) -> dict[str, Any]:
    """Return the interview's application, refusing a contradictory state.

    This is what stops, for example, confirming an interview whose application has
    already been rejected, or acting on an interview whose application vanished.
    Raises ``WorkflowError`` when the state cannot be used.
    """
    application = applications.get_application(interview.get("application_id"), data_dir)
    if application is None:
        raise WorkflowError("The application linked to this interview could not be found.")
    if application.get("status") in applications.TERMINAL_STATUSES:
        raise WorkflowError(
            "This application is already closed, so the interview can no longer be changed."
        )
    return application


# ---------------------------------------------------------------------------
# Workflow actions
# ---------------------------------------------------------------------------
def request_interview(
    application: Any,
    requested_datetime: Any,
    meeting_url: Any = "",
    data_dir: Any = None,
) -> dict[str, Any]:
    """Business proposes an interview. Returns the new interview record.

    Raises ``WorkflowError`` when the application is unusable, the date/link is
    invalid, or an interview is already open for this application (which also
    prevents duplicates caused by Streamlit reruns).
    """
    if not isinstance(application, dict) or not application.get("id"):
        raise WorkflowError("That application could not be read.")

    findings = validate_interview_request(requested_datetime, meeting_url)
    if validation.has_errors(findings):
        messages = [f["message"] for f in findings if f["level"] == "error"]
        raise WorkflowError(" ".join(messages))

    if active_interview_for_application(application.get("id"), data_dir) is not None:
        raise WorkflowError("An interview is already open for this application.")

    if application.get("status") not in (
        applications.STATUS_SUBMITTED,
        applications.STATUS_SHORTLISTED,
        applications.STATUS_INTERVIEW_REQUESTED,
    ):
        raise WorkflowError(
            "An interview can only be requested for a submitted or shortlisted application."
        )

    interview = {
        "id": _new_id(),
        "application_id": application.get("id"),
        "gig_id": application.get("gig_id"),
        "gig_title": application.get("gig_title") or "Untitled gig",
        "profile_id": application.get("profile_id"),
        "student_name": application.get("student_name") or "Unnamed student",
        "requested_datetime": normalize_datetime(requested_datetime),
        "alternative_datetime": "",
        "confirmed_datetime": "",
        "meeting_url": str(meeting_url or "").strip(),
        "status": INTERVIEW_REQUESTED,
        "history": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    _log(interview, "business", "request_interview", interview["requested_datetime"])

    # Save the interview first: if that write fails, the application status is
    # left untouched rather than pointing at an interview that does not exist.
    saved = _save(interview, data_dir)
    applications.update_status(
        application.get("id"), applications.STATUS_INTERVIEW_REQUESTED, data_dir
    )
    return saved


def respond_to_interview(
    interview_id: Any,
    action: str,
    alternative_datetime: Any = "",
    profile_id: Any = None,
    data_dir: Any = None,
) -> dict[str, Any]:
    """Student action: accept, decline, or propose an alternative time.

    When ``profile_id`` is given the interview must belong to that profile, so a
    student can never answer another local profile's interview. Accepting does
    **not** confirm the interview: it moves to ``accepted`` and waits for the
    business to confirm.
    """
    interview = get_interview(interview_id, data_dir)
    if interview is None:
        raise WorkflowError("That interview request could not be found.")

    if profile_id is not None and interview.get("profile_id") != profile_id:
        raise WorkflowError("That interview request belongs to a different profile.")

    allowed = STUDENT_ACTIONS.get(action)
    if allowed is None:
        raise WorkflowError(f"'{action}' is not something a student can do here.")
    if interview.get("status") not in allowed:
        raise WorkflowError(
            f"This interview is '{INTERVIEW_STATUS_LABELS.get(interview.get('status'), interview.get('status'))}', "
            f"so you cannot {action.replace('_', ' ')} it."
        )

    _guard_application(interview, data_dir)
    application_id = interview.get("application_id")

    if action == "accept":
        interview["status"] = INTERVIEW_ACCEPTED
    elif action == "decline":
        interview["status"] = INTERVIEW_DECLINED
    else:  # propose_alternative
        findings = validate_datetime(alternative_datetime, "Alternative date and time")
        if validation.has_errors(findings):
            raise WorkflowError(" ".join(f["message"] for f in findings if f["level"] == "error"))
        interview["alternative_datetime"] = normalize_datetime(alternative_datetime)
        interview["status"] = INTERVIEW_ALTERNATIVE_PROPOSED

    _log(interview, "student", action, interview.get("alternative_datetime", ""))
    interview["updated_at"] = _now()

    # Save the interview first so a failure cannot change the application alone.
    saved = _save(interview, data_dir)

    if action == "decline":
        applications.update_status(application_id, applications.STATUS_SHORTLISTED, data_dir)
    # accept and propose_alternative keep the application at interview_requested
    # until the business confirms the agreed time.

    return saved


def business_respond(
    interview_id: Any,
    action: str,
    data_dir: Any = None,
) -> dict[str, Any]:
    """Business action: confirm or decline an agreed time, or cancel a request.

    ``confirm`` (alias ``accept_alternative``) finalises the agreed time and
    records it in ``confirmed_datetime`` so the final decision keeps the exact
    time. ``decline`` (alias ``decline_alternative``) and ``cancel`` close the
    interview without confirming.
    """
    interview = get_interview(interview_id, data_dir)
    if interview is None:
        raise WorkflowError("That interview request could not be found.")

    allowed = BUSINESS_ACTIONS.get(action)
    if allowed is None:
        raise WorkflowError(f"'{action}' is not something a business can do here.")
    if interview.get("status") not in allowed:
        raise WorkflowError(
            f"This interview is '{INTERVIEW_STATUS_LABELS.get(interview.get('status'), interview.get('status'))}', "
            f"so you cannot {action.replace('_', ' ')} it."
        )

    _guard_application(interview, data_dir)
    application_id = interview.get("application_id")
    confirming = action in _CONFIRMING_ACTIONS

    if confirming:
        agreed = (
            interview.get("alternative_datetime")
            or interview.get("requested_datetime")
            or ""
        )
        interview["confirmed_datetime"] = agreed
        interview["status"] = INTERVIEW_CONFIRMED
    else:  # decline, decline_alternative, or cancel
        interview["status"] = INTERVIEW_DECLINED

    _log(interview, "business", action, interview.get("confirmed_datetime", ""))
    interview["updated_at"] = _now()

    # Save the interview first so a failure cannot change the application alone.
    saved = _save(interview, data_dir)

    if confirming:
        applications.update_status(
            application_id, applications.STATUS_INTERVIEW_CONFIRMED, data_dir
        )
    else:
        applications.update_status(application_id, applications.STATUS_SHORTLISTED, data_dir)

    return saved


def decline_open_interviews_for_application(
    application_id: Any, actor: str = "business", data_dir: Any = None
) -> list[dict[str, Any]]:
    """Close any open interviews for an application.

    Used when an application is rejected: the interview and the application can
    never contradict each other (for example a rejected application still showing
    a confirmed interview).
    """
    closed: list[dict[str, Any]] = []
    for interview in interviews_for_application(application_id, data_dir):
        if interview.get("status") in OPEN_INTERVIEW_STATUSES:
            interview["status"] = INTERVIEW_DECLINED
            _log(interview, actor, "application_closed", "")
            interview["updated_at"] = _now()
            closed.append(_save(interview, data_dir))
    return closed
