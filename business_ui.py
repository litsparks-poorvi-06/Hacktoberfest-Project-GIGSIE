"""Business side of the interview loop: applicants and interview scheduling.

This is presentation only. Every rule and every write lives in the backend modules
(``applications.py``, ``interviews.py``, ``storage.py``) so the workflow can be
tested without Streamlit.

Honest scope - this is a prototype:

  * There are **no** real accounts, so Gigsie cannot verify which business a viewer
    is, or that they own a gig. Every applicant, application, and interview below is
    **local demonstration data** stored on this device.
  * Gigsie does **not** host video calls, send emails or calendar invites, or
    provide real-time messaging. Interview coordination is only the stored status.

Timezone convention: times are stored as plain local wall-clock text
(``YYYY-MM-DD HH:MM``). The interface states the device's timezone so nobody has to
guess which clock a time refers to.
"""

from __future__ import annotations

from html import escape as _escape
from typing import Any

import streamlit as st

import applications
from errors import WorkflowError
import interviews
import profiles
import storage
import ui_common


FLASH_KEY = "business_interview_flash"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _set_flash(level: str, message: str) -> None:
    st.session_state[FLASH_KEY] = {"level": level, "message": message}


def _render_flash() -> None:
    flash = st.session_state.pop(FLASH_KEY, None)
    if not isinstance(flash, dict):
        return
    level = flash.get("level")
    message = str(flash.get("message") or "")
    if level == "error":
        st.error(message)
    elif level == "warning":
        st.warning(message)
    else:
        st.success(message)


def _open_interviews(interviews_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        interview
        for interview in interviews_list
        if interview.get("status") in interviews.PENDING_BUSINESS_STATUSES
    ]


def _render_student_profile(profile_id: Any) -> None:
    """Show the applicant's saved local profile, if it still exists."""
    if not profile_id:
        return
    try:
        profile = profiles.load_profile(profile_id)
    except storage.StorageError as error:
        st.caption(f"The saved profile could not be read: {error}")
        return
    if not profile:
        st.caption("The student's saved local profile is no longer available.")
        return

    st.markdown(f"**{profile.get('display_name') or 'Unnamed student'}**")
    skills = profile.get("skills") or []
    if skills:
        st.markdown("**Skills:** " + ", ".join(str(skill) for skill in skills))
    if profile.get("experience_level"):
        st.caption(f"Experience level: {profile.get('experience_level')}")
    if profile.get("bio"):
        st.write(profile.get("bio"))
    links = profile.get("portfolio_links") or []
    if links:
        st.markdown("**Portfolio:** " + ", ".join(str(link) for link in links))
    if profile.get("available_time"):
        st.caption(f"Availability: {profile.get('available_time')}")
    elif profile.get("weekly_hours") is not None:
        st.caption(f"Availability: {profile.get('weekly_hours')} hrs/week")
    st.caption("Self-reported by the student. Gigsie does not verify profiles.")


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def _do_request_interview(application: dict[str, Any], when: str, url: str) -> None:
    try:
        interviews.request_interview(application, when, url)
    except WorkflowError as error:
        _set_flash("error", f"The interview was **not** requested. {error}")
    except storage.StorageError as error:
        _set_flash("error", f"The interview could not be saved, so it was not created: {error}")
    else:
        _set_flash(
            "success",
            "Interview requested. The student will see it in their Interviews tab.",
        )
    st.rerun()


def _do_business_response(interview: dict[str, Any], action: str, success: str) -> None:
    try:
        interviews.business_respond(interview.get("id"), action)
    except WorkflowError as error:
        _set_flash("error", f"The interview was **not** changed. {error}")
    except storage.StorageError as error:
        _set_flash("error", f"The change could not be saved: {error}")
    else:
        _set_flash("success", success)
    st.rerun()


def _do_application_status(application: dict[str, Any], new_status: str, success: str) -> None:
    try:
        applications.update_status(application.get("id"), new_status)
        if new_status == applications.STATUS_REJECTED:
            # Keep the records consistent: a rejected application cannot still have
            # an open interview.
            interviews.decline_open_interviews_for_application(application.get("id"))
    except WorkflowError as error:
        _set_flash("error", f"The application status was **not** changed. {error}")
    except storage.StorageError as error:
        _set_flash("error", f"The change could not be saved: {error}")
    else:
        _set_flash("success", success)
    st.rerun()


# ---------------------------------------------------------------------------
# Interview request form (shown on an eligible applicant card)
# ---------------------------------------------------------------------------
def _render_request_interview_form(application: dict[str, Any]) -> None:
    app_id = application.get("id")
    st.markdown("**Request an interview**")
    when = st.text_input(
        "Proposed date and time (YYYY-MM-DD HH:MM)",
        key=f"biz_when_{app_id}",
        placeholder="2026-10-25 15:00",
    )
    url = st.text_input(
        "Meeting link (optional)",
        key=f"biz_url_{app_id}",
        placeholder="https://meet.example.com/abc",
    )
    st.caption(
        f"Times use this device's local time ({interviews.local_timezone_label()}). "
        "Gigsie does not create or verify the meeting room - the link is only stored."
    )
    if st.button(
        "Request interview",
        type="primary",
        key=f"biz_request_{app_id}",
        use_container_width=True,
    ):
        _do_request_interview(application, when, url)


# ---------------------------------------------------------------------------
# Applicant cards
# ---------------------------------------------------------------------------
def _render_applicant_card(application: dict[str, Any], gig: dict[str, Any]) -> None:
    app_id = application.get("id")
    status = application.get("status")

    ui_common.panel(
        f"{application.get('student_name') or 'Unnamed student'}",
        f"{gig.get('title') or 'Untitled gig'} · applied {application.get('created_at')}",
        body=(
            f"<div>{ui_common.status_pill(status, applications.STATUS_LABELS.get(status, status))}</div>"
            f'<p class="gs-note">Application ID {_escape(str(app_id))}</p>'
        ),
        tags=ui_common.tags(ui_common.gig_skills(gig), limit=4),
    )

    with st.expander("Proposal"):
        st.write(application.get("proposal") or "_(no proposal text saved)_")

    with st.expander("Student profile"):
        _render_student_profile(application.get("profile_id"))

    try:
        existing = interviews.active_interview_for_application(app_id)
    except storage.StorageError as error:
        st.error(f"This applicant's interviews could not be read: {error}")
        return

    if existing:
        istatus = existing.get("status")
        st.caption(
            "Interview: "
            f"**{interviews.INTERVIEW_STATUS_LABELS.get(istatus, istatus)}** — "
            "manage it under 'Interview requests & responses' above."
        )
    elif status in (applications.STATUS_SUBMITTED, applications.STATUS_SHORTLISTED):
        _render_request_interview_form(application)
    elif status == applications.STATUS_REJECTED:
        st.caption("This application was rejected.")
    else:
        st.caption("No open interview for this application.")

    if status not in applications.TERMINAL_STATUSES:
        col_shortlist, col_reject = st.columns(2)
        with col_shortlist:
            if st.button(
                "Shortlist",
                key=f"biz_shortlist_{app_id}",
                use_container_width=True,
                disabled=(status == applications.STATUS_SHORTLISTED),
            ):
                _do_application_status(
                    application,
                    applications.STATUS_SHORTLISTED,
                    "Applicant shortlisted.",
                )
        with col_reject:
            if st.button(
                "Reject",
                key=f"biz_reject_{app_id}",
                use_container_width=True,
            ):
                _do_application_status(
                    application,
                    applications.STATUS_REJECTED,
                    "Application rejected. Any open interview was closed.",
                )


# ---------------------------------------------------------------------------
# Interview requests & responses
# ---------------------------------------------------------------------------
def _render_business_interview_card(interview: dict[str, Any]) -> None:
    interview_id = interview.get("id")
    status = interview.get("status")

    with st.container(border=True):
        st.markdown(
            f"**{interview.get('student_name') or 'Unnamed student'}** — "
            f"{interview.get('gig_title') or 'Untitled gig'}"
        )
        st.markdown(
            ui_common.status_pill(status, interviews.INTERVIEW_STATUS_LABELS.get(status, status)),
            unsafe_allow_html=True,
        )
        st.caption(f"Business proposed: {interview.get('requested_datetime') or '—'}")
        if interview.get("alternative_datetime"):
            st.caption(f"Student proposed: {interview.get('alternative_datetime')}")
        if interview.get("confirmed_datetime"):
            st.caption(f"Confirmed time: {interview.get('confirmed_datetime')}")
        if interview.get("meeting_url"):
            st.caption(f"Meeting link: {interview.get('meeting_url')}")
        else:
            st.caption("No meeting link provided.")

        if status in (interviews.INTERVIEW_ACCEPTED, interviews.INTERVIEW_ALTERNATIVE_PROPOSED):
            col_confirm, col_decline = st.columns(2)
            with col_confirm:
                if st.button(
                    "Confirm this time",
                    type="primary",
                    key=f"biz_confirm_{interview_id}",
                    use_container_width=True,
                ):
                    _do_business_response(
                        interview, "confirm", "Interview confirmed. The agreed time is saved."
                    )
            with col_decline:
                if st.button(
                    "Decline",
                    key=f"biz_decline_{interview_id}",
                    use_container_width=True,
                ):
                    _do_business_response(
                        interview, "decline", "Interview declined."
                    )
        elif status == interviews.INTERVIEW_REQUESTED:
            if st.button(
                "Cancel request",
                key=f"biz_cancel_{interview_id}",
                use_container_width=True,
            ):
                _do_business_response(interview, "cancel", "Interview request cancelled.")

        history = interview.get("history") or []
        if history:
            with st.expander("History"):
                for entry in history:
                    st.caption(
                        f"{entry.get('at')} · {entry.get('actor')} · "
                        f"{entry.get('action')} {entry.get('note') or ''}".strip()
                    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def render_business_interviews() -> None:
    ui_common.section_heading(
        "Applicants & interviews",
        "Real proposals against gigs saved on this device.",
    )
    ui_common.panel(
        "Local demonstration data",
        "No accounts, so identity cannot be verified",
        body=(
            "<p>These are <b>local demonstration data</b>. Gigsie "
            "<b>cannot verify who a business is</b> or that you own a gig, and nothing "
            "is booked on an external calendar.</p>"
        ),
        footer=ui_common.tags(["No verified accounts", "No calendar booking"]),
    )

    _render_flash()

    try:
        gigs = storage.load_gigs()
    except storage.StorageError as error:
        st.error(f"Gigs could not be read: {error}")
        return

    gigs_by_id = {gig.get("id"): gig for gig in gigs if gig.get("id")}

    try:
        all_applications = applications.all_applications()
        all_interviews = storage.load_interviews()
    except storage.StorageError as error:
        st.error(f"Applicant or interview data could not be read: {error}")
        return

    # Only applications whose gig really exists in local storage are shown; we never
    # invent a gig, student, or activity.
    linked = [
        application
        for application in all_applications
        if application.get("gig_id") in gigs_by_id
    ]

    if not linked:
        st.caption(
            "No applications yet. When a student applies to a gig saved here, it will "
            "appear below."
        )
        return

    linked_gig_ids = {application.get("gig_id") for application in linked}

    ui_common.section_heading(
        "Interview requests & responses",
        "Times use this device's local time; only the stored status is kept.",
    )
    mine = [
        interview
        for interview in all_interviews
        if interview.get("gig_id") in linked_gig_ids
    ]
    pending = [i for i in mine if i.get("status") in interviews.PENDING_BUSINESS_STATUSES]
    if not pending:
        st.caption("Nothing needs a response right now.")
    else:
        st.caption(
            f"{len(pending)} interview request(s) need a response. Times use this "
            f"device's local time ({interviews.local_timezone_label()})."
        )
        for interview in pending:
            _render_business_interview_card(interview)

    closed = [i for i in mine if i not in pending]
    if closed:
        with st.expander(f"Closed interviews ({len(closed)})"):
            for interview in closed:
                _render_business_interview_card(interview)

    ui_common.section_heading("Applicants by gig", "Grouped by the gig they applied to.")
    ordered_gig_ids: list[Any] = []
    for application in linked:
        gig_id = application.get("gig_id")
        if gig_id not in ordered_gig_ids:
            ordered_gig_ids.append(gig_id)

    for gig_id in ordered_gig_ids:
        gig = gigs_by_id.get(gig_id) or {}
        group = [a for a in linked if a.get("gig_id") == gig_id]
        heading = f"{gig.get('title') or 'Untitled gig'}"
        if gig.get("sample"):
            st.markdown(f"##### {heading} " + ui_common.sample_tag(), unsafe_allow_html=True)
        else:
            st.markdown(f"##### {heading}")
        st.caption(f"Gig ID: {gig_id} · {len(group)} applicant(s)")
        for application in group:
            _render_applicant_card(application, gig)
