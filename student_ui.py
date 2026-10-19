"""Student side of Gigsie: profile, browse, apply, and practice assessments.

Honest scope - this is a prototype:

  * There are **no** real user accounts or authentication. A "profile" is a JSON
    record saved locally on this device, and its id only links a student to the
    applications and assessment results they create inside this prototype.
  * Skills are **self-reported**. Matching is advice, not a hiring decision, and
    Gigsie never verifies a skill.
  * The proposal the student submits is written by the student. The only AI use in
    the student area is the *practice* skill assessment, where the model writes the
    questions but **Python grades them** - never the model. Results are labelled as
    AI-generated practice, not a certification, and never block applying for a gig.

This module is presentation only. Every rule and every write lives in the backend
modules (``profiles.py``, ``applications.py``, ``assessments.py``, ``validation.py``,
``storage.py``) so they can be tested without Streamlit.
"""

from __future__ import annotations

from datetime import datetime
from html import escape as _escape
from typing import Any

import streamlit as st

import applications
import assessments
from errors import WorkflowError
import fairscope
from gig_workflow import join_lines
import gigsie_ai
import interviews
import profiles
import storage
import ui_common
import validation


# ---------------------------------------------------------------------------
# Small guards and helpers
# ---------------------------------------------------------------------------
def _top_bar() -> None:
    """Kept for compatibility: the back control now lives in the page header."""
    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Back to start", key="student_back_to_landing"):
            ui_common.go(ui_common.VIEW_HOME, ui_common.SEC_OVERVIEW)


def _student_header(section: str) -> None:
    """Compact top header for every student page.

    The profile area shows the real local profile - never an invented avatar,
    name, or notification count.
    """
    active = _active_profile()
    name = str(active.get("display_name") or "") if active else ""
    sub = f"Student profile · {active.get('id')}" if active else ""
    ui_common.top_header(
        crumb=["Student", ui_common.SECTION_LABEL.get(section, "Student overview")],
        role=ui_common.ROLE_STUDENT,
        back_key="student_back_to_landing",
        profile_name=name,
        profile_sub=sub,
        primary_label="Find Work",
        primary_target=(ui_common.VIEW_STUDENT, ui_common.SEC_FIND_WORK),
    )


def _section_jump(current: str) -> None:
    """Deprecated: the sidebar is the single navigation, so no in-page jump bar."""
    return


def _active_profile() -> dict[str, Any] | None:
    """The profile currently being used, or None for "creating a new one"."""
    profile = st.session_state.get("student_profile")
    if isinstance(profile, dict) and profile.get("id"):
        return profile
    return None


def _safe_profiles() -> tuple[list[dict[str, Any]], str | None]:
    try:
        return profiles.list_profiles(), None
    except storage.StorageError as error:
        return [], str(error)


def _levels_to_text(profile: dict[str, Any] | None) -> str:
    levels = (profile or {}).get("skill_levels")
    if not isinstance(levels, dict):
        return ""
    return join_lines([f"{name}: {str(level).title()}" for name, level in levels.items()])


def _experience_index(profile: dict[str, Any] | None) -> int:
    level = str((profile or {}).get("experience_level") or "").strip().lower()
    choices = [choice.lower() for choice in profiles.SKILL_LEVEL_CHOICES]
    return choices.index(level) if level in choices else 0


def _first_portfolio(profile: dict[str, Any] | None) -> str:
    links = (profile or {}).get("portfolio_links")
    if isinstance(links, list) and links:
        return str(links[0])
    return ""


def _as_list(value: Any) -> list[str]:
    """Coerce a string or list into a clean list of strings."""
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _brief_of(gig: dict[str, Any]) -> dict[str, Any]:
    brief = gig.get("brief") if isinstance(gig, dict) else None
    return brief if isinstance(brief, dict) else {}


def _gig_objective(gig: dict[str, Any]) -> str:
    """Read the objective from either the new or the old brief schema."""
    brief = _brief_of(gig)
    return str(
        gig.get("objective")
        or brief.get("objective")
        or brief.get("project_objective")
        or ""
    ).strip()


def _gig_acceptance(gig: dict[str, Any]) -> list[str]:
    return _as_list(_brief_of(gig).get("acceptance_criteria"))


def _budget_text(gig: dict[str, Any]) -> str:
    budget = gig.get("budget_inr")
    if budget in (None, "", 0, 0.0):
        return "Not specified"
    try:
        return f"{float(budget):,.0f} INR"
    except (TypeError, ValueError):
        return "Not specified"


def _has_hours(profile: dict[str, Any] | None) -> bool:
    hours = (profile or {}).get("weekly_hours")
    return isinstance(hours, (int, float)) and hours > 0


def _profile_checklist_items(
    profile: dict[str, Any] | None,
) -> list[tuple[str, bool, bool]]:
    """Return ``(label, done, required)`` for the onboarding checklist.

    Each item reflects only what the profile actually contains, so a missing
    required field is obvious without inventing any data.
    """
    profile = profile or {}
    return [
        ("Display name", bool(str(profile.get("display_name") or "").strip()), True),
        ("At least one skill", bool(_as_list(profile.get("skills"))), True),
        ("Weekly availability", _has_hours(profile), True),
        ("Short biography", bool(str(profile.get("bio") or "").strip()), False),
        ("Portfolio link", bool(_as_list(profile.get("portfolio_links"))), False),
    ]


def _render_profile_checklist(profile: dict[str, Any] | None) -> None:
    """Show, at a glance, which profile basics are in place - no scores, no metrics."""
    chips: list[str] = []
    for label, done, required in _profile_checklist_items(profile):
        if done:
            chips.append(ui_common.chip(f"✓ {label}", "ok"))
        elif required:
            chips.append(ui_common.chip(f"⚠ {label} required", "warn"))
        else:
            chips.append(ui_common.chip(label, "neutral"))

    if profile:
        lead = (
            "Your profile is saved locally. Required items still missing are shown in "
            "amber - add them so gig matches are meaningful."
        )
    else:
        lead = (
            "Fill in the form below. Everyone starts somewhere: list the skills you "
            "honestly have, and you can add more later."
        )
    st.markdown(
        f'<div class="gs-card"><h4>Profile checklist</h4><p>{lead}</p>{"".join(chips)}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Profile tab
# ---------------------------------------------------------------------------
def render_profile_tab() -> None:
    ui_common.section_heading(
        "Your student profile",
        "Self-reported skills and details saved on this device only.",
    )
    st.caption(
        "There are no real accounts, passwords, or authentication here. The skills you "
        "list are self-reported and Gigsie does not verify them."
    )

    flash = st.session_state.pop("student_profile_flash", None)
    if flash:
        st.success(flash)

    saved, error = _safe_profiles()
    if error:
        st.error(f"Saved profiles could not be read: {error}")

    if saved:
        labels = [
            f"{profile.get('display_name') or 'Unnamed student'} — {profile.get('id')}"
            for profile in saved
        ]
        choice = st.selectbox("Load a previously saved profile", labels, index=0)
        col_load, col_new = st.columns(2)
        with col_load:
            if st.button("Load this profile", use_container_width=True, key="student_load"):
                st.session_state["student_profile"] = saved[labels.index(choice)]
                st.rerun()
        with col_new:
            if st.button(
                "Start a new blank profile",
                use_container_width=True,
                key="student_new_profile",
            ):
                st.session_state["student_profile"] = None
                st.rerun()
    else:
        st.caption("No profiles saved yet. Fill in the form below to create one.")

    active = _active_profile()
    if active:
        st.success(
            f"Active profile: **{active.get('display_name')}** (`{active.get('id')}`)"
        )
    else:
        st.caption("You are creating a new profile.")

    _render_profile_checklist(active)

    _render_profile_form(active)


def _render_profile_form(active: dict[str, Any] | None) -> None:
    editing = bool(active and active.get("id"))
    form_key = f"student_profile_form_{active.get('id') if editing else 'new'}"

    with st.form(form_key):
        name = st.text_input(
            "Display name *",
            value=(active or {}).get("display_name") or "",
        )
        skills_text = st.text_area(
            "Skills (one per line) *",
            value=join_lines((active or {}).get("skills")),
            height=120,
            placeholder="Canva\nCopywriting\nBasic graphic design",
        )
        levels_text = st.text_area(
            "Skill levels (optional) — one per line as 'Skill: Beginner'",
            value=_levels_to_text(active),
            height=90,
            placeholder="Canva: Beginner\nCopywriting: Intermediate",
        )
        experience = st.selectbox(
            "Overall experience level",
            list(profiles.SKILL_LEVEL_CHOICES),
            index=_experience_index(active),
        )
        bio = st.text_area(
            "Short biography (optional)",
            value=(active or {}).get("bio") or "",
            height=100,
            placeholder="A sentence or two about you and the kind of work you enjoy.",
        )
        portfolio = st.text_input(
            "Portfolio or project URL (optional)",
            value=_first_portfolio(active),
            placeholder="https://example.com/my-work",
        )
        hours = st.number_input(
            "Weekly availability (hours per week) *",
            min_value=0.0,
            max_value=168.0,
            step=1.0,
            value=float((active or {}).get("weekly_hours") or 0.0),
        )

        save_clicked = st.form_submit_button(
            "Save profile", type="primary", use_container_width=True
        )
        save_as_new_clicked = False
        if editing:
            save_as_new_clicked = st.form_submit_button(
                "Save as a new profile", use_container_width=True
            )

    if not (save_clicked or save_as_new_clicked):
        return

    values = {
        "display_name": name,
        "skills": skills_text,
        "skill_levels": levels_text,
        "experience_level": experience,
        "bio": bio,
        "portfolio_links": [portfolio],
        "weekly_hours": hours,
    }

    findings = profiles.validate_profile_input(values)
    ui_common.show_findings(findings, ok_text=None)

    if validation.has_errors(findings):
        st.error("The profile was **not** saved. Please fix the items above.")
        return

    target_id = None if (save_as_new_clicked or not editing) else active.get("id")
    try:
        saved = profiles.save_profile(values, profile_id=target_id)
    except WorkflowError as error:
        st.error(f"The profile was **not** saved. {error}")
        return
    except storage.StorageError as error:
        st.error(f"The profile could not be saved: {error}")
        return

    st.session_state["student_profile"] = saved
    st.session_state["student_profile_flash"] = (
        f"Profile saved for **{saved.get('display_name')}** (`{saved.get('id')}`)."
    )
    st.rerun()


# ---------------------------------------------------------------------------
# Browse gigs tab
# ---------------------------------------------------------------------------
def render_browse_tab() -> None:
    ui_common.section_heading(
        "Browse published gigs",
        "Published first, labelled samples last.",
    )

    try:
        gigs = storage.load_gigs()
    except storage.StorageError as error:
        st.error(f"Gigs could not be read: {error}")
        return

    published = [gig for gig in gigs if not gig.get("sample")]
    samples = [gig for gig in gigs if gig.get("sample")]
    ordered = published + samples

    if not ordered:
        st.info(
            "No gigs are available yet. A business can create one in the **Business** "
            "area; once it is published, it will appear here automatically."
        )
        return

    st.caption(
        "Sample gigs stay labelled SAMPLE and cannot be applied for."
    )

    profile = _active_profile()
    if not profile:
        st.warning(
            "Create or load a profile in the Profile tab to see which of your skills "
            "match each gig."
        )

    _render_gig_cards(ordered, profile)

    display: list[str] = []
    for gig in ordered:
        tag = " [SAMPLE]" if gig.get("sample") else ""
        title = ui_common.gig_title(gig)
        display.append(f"{title}{tag} · {gig.get('id')}")

    selected_id = st.session_state.get("student_selected_gig")
    index = 0
    if selected_id:
        ids = [str(gig.get("id")) for gig in ordered]
        if selected_id in ids:
            index = ids.index(selected_id)

    choice = st.selectbox(
        "Choose a gig to view", display, index=index, key="student_gig_choice"
    )
    gig = ordered[display.index(choice)]
    st.session_state["student_selected_gig"] = gig.get("id")

    _render_gig_detail(gig, profile)


def _match_line(gig: dict[str, Any], profile: dict[str, Any] | None) -> str:
    """A real, deterministic match summary - never estimated by the model."""
    if not profile:
        return ""
    match = validation.match_gig_to_skills(gig, profile)
    parts: list[str] = []
    if match["score"] is not None:
        parts.append(f"Skill match {match['score']}%")
    if match["matched"]:
        parts.append("you list " + ", ".join(match["matched"]))
    if match["missing"]:
        parts.append("not in your profile: " + ", ".join(match["missing"]))
    return " · ".join(parts)


def _render_gig_cards(gigs: list[dict[str, Any]], profile: dict[str, Any] | None) -> None:
    """A scannable grid of gig cards, each with a real 'View Gig' action."""
    if not gigs:
        return
    ordered = _order_gigs(gigs, profile)
    for start in range(0, len(ordered), 2):
        columns = st.columns(2, gap="medium")
        for offset, gig in enumerate(ordered[start : start + 2]):
            with columns[offset]:
                st.markdown(
                    ui_common.gig_card(
                        gig,
                        description=str(gig.get("desired_outcome") or "")
                        or ui_common.gig_objective(gig),
                        meta_right=str(gig.get("created_at") or "")[:10],
                        match_line=_match_line(gig, profile),
                        fill=True,
                    ),
                    unsafe_allow_html=True,
                )
                if st.button(
                    "View Gig",
                    key=f"student_view_{gig.get('id')}",
                    use_container_width=True,
                ):
                    st.session_state["student_selected_gig"] = gig.get("id")
                    st.rerun()


def _order_gigs(
    gigs: list[dict[str, Any]], profile: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Use the existing deterministic ranking so better matches surface first."""
    if not profile:
        return gigs
    try:
        ranked = validation.rank_gigs(gigs, profile)
    except Exception:  # pragma: no cover - ranking is advisory only
        return gigs
    return [item["gig"] for item in ranked if isinstance(item, dict) and "gig" in item]


def _render_gig_detail(gig: dict[str, Any], profile: dict[str, Any] | None) -> None:
    title = ui_common.gig_title(gig)
    if gig.get("sample"):
        st.markdown(f"### {title} " + ui_common.sample_tag(), unsafe_allow_html=True)
    else:
        st.markdown(f"### {title}")

    pairs = [("Business", ui_common.gig_context(gig))]
    if gig.get("id"):
        pairs.append(("Gig ID", str(gig.get("id"))))
    pairs.append(("Budget", ui_common.gig_budget(gig)))
    pairs.append(("Deadline", str(gig.get("deadline") or "Not specified")))
    ui_common.panel(
        "Gig summary",
        "Everything below comes from the published gig record",
        body=ui_common.key_values(pairs),
        tags=ui_common.tags(ui_common.gig_skills(gig)),
        fill=True,
    )

    objective = _gig_objective(gig)
    if objective:
        st.markdown("**Objective**")
        st.write(objective)

    outcome = str(gig.get("desired_outcome") or "").strip()
    if outcome and outcome != objective:
        st.markdown("**Outcome the business wants**")
        st.write(outcome)

    work_needed = str(gig.get("work_needed") or "").strip()
    if work_needed and work_needed not in (objective, outcome):
        st.markdown("**What the business needs**")
        st.write(work_needed)

    st.markdown("**Deliverables**")
    ui_common.bullet_list(validation.get_deliverables(gig), "No deliverables listed.")

    st.markdown("**Required skills**")
    ui_common.bullet_list(validation.get_required_skills(gig), "No specific skills listed.")

    st.markdown("**Acceptance criteria**")
    ui_common.bullet_list(_gig_acceptance(gig), "No acceptance criteria listed.")

    _render_passport_block(gig)

    _render_match_block(gig, profile)

    st.divider()
    _render_apply_section(gig, profile)


def _render_passport_block(gig: dict[str, Any]) -> None:
    """Show the published Gig Passport: the agreed scope and its boundaries.

    The passport is saved with the gig (FairScope). Older gigs and the labelled
    samples have no stored passport, so one is derived from their brief - the
    same honest "needs clarification" states are shown either way.
    """
    passport = fairscope.passport_for_gig(gig)
    sections = passport.get("sections") or {}
    if not sections:
        return

    with st.expander("🛂 Gig Passport (agreed scope)", expanded=False):
        st.caption(
            "The scope both sides work from. Where something was not specified, it is "
            "marked **Needs clarification** rather than invented."
        )
        for key in (
            "objective",
            "included_work",
            "exclusions",
            "client_responsibilities",
            "revision_expectations",
            "open_questions",
            "assumptions",
            "scope_warnings",
        ):
            section = sections.get(key)
            if not section:
                continue
            st.markdown(f"**{section.get('label')}**")
            ui_common.passport_value(section)


def _render_match_block(gig: dict[str, Any], profile: dict[str, Any] | None) -> None:
    st.divider()
    st.markdown("**How well this matches your profile**")
    st.caption(
        "Calculated in Python from the skills this gig requires and the skills you "
        "listed - never estimated by the AI, and never a verification of your skills."
    )

    # Deterministic matching only - the AI never invents a percentage.
    match = validation.match_gig_to_skills(gig, profile or {})

    if match["score"] is None:
        st.metric("Skill match", "Not scored")
    else:
        st.metric("Skill match", f"{match['score']}%")

    if match["matched"]:
        st.markdown("**Matched required skills:** " + ", ".join(match["matched"]))
    if match["missing"]:
        st.markdown(
            "**Required skills not listed in your profile:** " + ", ".join(match["missing"])
        )
    if profile and not _as_list(profile.get("skills")):
        st.info(
            "Your profile lists no skills yet, so no match score can be calculated. "
            "Add the skills you honestly have in the **Profile** tab to see how you line "
            "up with this gig."
        )

    st.markdown("**Why this result**")
    for reason in match["reasons"]:
        st.markdown(f"- {reason}")

    st.caption(match["availability_note"])
    st.caption(match["disclaimer"])


# ---------------------------------------------------------------------------
# Apply section (inside the browse tab, for the selected gig)
# ---------------------------------------------------------------------------
def _render_proposal_brief(gig: dict[str, Any], profile: dict[str, Any]) -> None:
    """Remind the student what this gig needs before they write the proposal.

    Shows the gig's own objective, deliverables, and required skills, plus the
    skills the profile already lists and any it does not - computed in Python,
    never invented.
    """
    objective = _gig_objective(gig)
    deliverables = validation.get_deliverables(gig)
    required = validation.get_required_skills(gig)
    match = validation.match_gig_to_skills(gig, profile)

    with st.container(border=True):
        st.markdown("##### What this gig needs")
        if objective:
            st.markdown(f"**Objective:** {objective}")
        st.markdown("**Deliverables**")
        ui_common.bullet_list(deliverables, "No deliverables listed.")
        st.markdown("**Skills the business requires**")
        ui_common.bullet_list(required, "No specific skills listed.")
        if match["matched"]:
            st.markdown(
                "**Your profile lists:** " + ", ".join(match["matched"])
            )
        if match["missing"]:
            st.markdown(
                "**Not in your profile (address these or ask):** "
                + ", ".join(match["missing"])
            )
        st.caption(
            "Explain which of your skills are relevant, how you would approach the work, "
            "and anything you need clarified. Only describe experience you actually have "
            "- the business reads this proposal directly."
        )


def _render_apply_section(gig: dict[str, Any], profile: dict[str, Any] | None) -> None:
    st.markdown("#### Apply for this gig")

    flash = st.session_state.pop("student_last_application", None)
    if isinstance(flash, dict) and flash.get("gig_id") == gig.get("id"):
        st.success(
            f"Application submitted. Your application ID is **{flash.get('id')}** "
            f"and the status is **Submitted**."
        )

    if not profile:
        st.info("Create a student profile in the Profile tab before applying.")
        return

    try:
        existing = applications.find_duplicate(profile.get("id"), gig.get("id"))
    except storage.StorageError as error:
        st.error(f"Your applications could not be read: {error}")
        return

    if existing:
        status = applications.STATUS_LABELS.get(existing.get("status"), existing.get("status"))
        st.info(
            f"You have already applied for this gig. Status: **{status}**. "
            "Each profile can apply to a gig once."
        )
        return

    gig_id = gig.get("id")
    proposal_key = f"student_proposal_{gig_id}"
    durable_key = f"student_proposal_text_{gig_id}"

    # Re-seed the editor from the saved copy when it comes back (Streamlit drops
    # widget state for widgets that were not rendered on the previous run).
    if proposal_key not in st.session_state:
        st.session_state[proposal_key] = st.session_state.get(durable_key, "")

    if st.session_state.get("student_review_gig") == gig_id:
        _render_review_step(gig, profile, durable_key)
        return

    _render_proposal_brief(gig, profile)
    st.caption(
        "Write a short proposal explaining why you fit this task. You can review it "
        "before you submit."
    )
    st.text_area(
        "Your proposal *",
        key=proposal_key,
        height=170,
        placeholder=(
            "I can design the Instagram posts because I have used Canva for two "
            "university projects and I write clear captions..."
        ),
    )
    if st.button("Review proposal", key=f"student_review_{gig_id}"):
        st.session_state[durable_key] = st.session_state.get(proposal_key, "")
        st.session_state["student_review_gig"] = gig_id
        st.rerun()


def _render_review_step(
    gig: dict[str, Any], profile: dict[str, Any], durable_key: str
) -> None:
    gig_id = gig.get("id")
    text = str(st.session_state.get(durable_key) or "").strip()

    st.markdown("##### Review your proposal")
    st.caption(
        f"Applying for: **{gig.get('title') or 'Untitled gig'}**. This is exactly what "
        "will be sent to the business."
    )
    with st.container(border=True):
        st.write(text if text else "_(empty)_")

    findings = applications.validate_proposal(text)
    for finding in findings:
        if finding.get("level") == "error":
            st.error(finding["message"])
        else:
            st.warning(finding["message"])
    if not findings:
        st.caption("The proposal looks ready to submit.")

    col_submit, col_edit = st.columns(2)
    with col_submit:
        submit_clicked = st.button(
            "Submit application",
            type="primary",
            use_container_width=True,
            key=f"student_submit_{gig_id}",
        )
    with col_edit:
        if st.button(
            "Back to editing",
            use_container_width=True,
            key=f"student_edit_{gig_id}",
        ):
            st.session_state["student_review_gig"] = None
            st.rerun()

    if not submit_clicked:
        return

    if validation.has_errors(findings):
        st.error("This application was **not** submitted. Fix the proposal and review again.")
        return

    try:
        record = applications.submit_application(profile, gig, text)
    except WorkflowError as error:
        st.error(f"This application was **not** submitted. {error}")
        return
    except storage.StorageError as error:
        st.error(f"This application could not be saved: {error}")
        return

    st.session_state["student_review_gig"] = None
    st.session_state["student_last_application"] = record
    st.rerun()


# ---------------------------------------------------------------------------
# My applications tab
# ---------------------------------------------------------------------------
def render_my_applications_tab() -> None:
    ui_common.section_heading(
        "Your applications",
        "Proposals you submitted, with their current stored status.",
    )

    profile = _active_profile()
    if not profile:
        st.info("Create a profile first - applications are linked to your profile.")
        return

    try:
        mine = applications.applications_for_profile(profile.get("id"))
    except storage.StorageError as error:
        st.error(f"Your applications could not be read: {error}")
        return

    if not mine:
        st.info(
            "You have not applied for any gigs yet. Use the **Browse gigs** tab to find "
            "one that matches your skills."
        )
        return

    st.caption(
        f"{len(mine)} application(s) submitted from this profile. Statuses are stored "
        "locally; this prototype sends no emails and has no real accounts."
    )

    for application in mine:
        status = application.get("status")
        with st.container(border=True):
            st.markdown(f"**{application.get('gig_title') or 'Untitled gig'}**")
            st.markdown(
                ui_common.status_pill(
                    status, applications.STATUS_LABELS.get(status, status)
                ),
                unsafe_allow_html=True,
            )
            meaning = applications.STATUS_MEANINGS.get(status)
            if meaning:
                st.caption(meaning)
            st.caption(
                f"Application ID: {application.get('id')} · "
                f"Submitted: {application.get('created_at')}"
            )
            with st.expander("View proposal"):
                st.write(application.get("proposal") or "")


# ---------------------------------------------------------------------------
# Skill assessments tab
# ---------------------------------------------------------------------------
def _safe_gigs() -> list[dict[str, Any]]:
    try:
        return storage.load_gigs()
    except storage.StorageError:
        return []


def _assessment_skill_options(profile: dict[str, Any] | None) -> list[str]:
    """Skills the student can practise: their own skills plus gig requirements."""
    options: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = str(value or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            options.append(text)

    for skill in (profile or {}).get("skills") or []:
        add(skill)
    for gig in _safe_gigs():
        for skill in validation.get_required_skills(gig):
            add(skill)
    return options


def _gig_for_skill(skill: Any) -> dict[str, Any] | None:
    """Return a gig whose required skills include ``skill``, for extra context."""
    normalized = validation.normalize_skill(skill)
    for gig in _safe_gigs():
        for required in validation.get_required_skills(gig):
            if validation.normalize_skill(required) == normalized:
                return gig
    return None


def _reset_assessment() -> None:
    st.session_state["student_assessment_private"] = None
    st.session_state["student_assessment_started"] = False
    st.session_state["student_assessment_started_at"] = ""
    st.session_state["student_assessment_graded"] = None


def _started_datetime() -> datetime | None:
    raw = st.session_state.get("student_assessment_started_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def render_assessments_tab() -> None:
    ui_common.section_heading(
        "Skill assessments",
        "AI-generated practice questions, graded locally in Python.",
    )
    st.info(
        "Short **AI-generated practice** assessments for one skill. They are **not a "
        "certification** and are **not verified**. Your score is calculated in Python "
        "from the answers you choose. Taking - or skipping - an assessment never stops "
        "you from applying for a gig."
    )

    profile = _active_profile()
    error = st.session_state.pop("student_assessment_error", None)
    if error:
        st.error(error)

    if not profile:
        st.info(
            "Create or load a profile first - practice results are saved against your "
            "local profile."
        )
        return

    private = st.session_state.get("student_assessment_private")
    graded = st.session_state.get("student_assessment_graded")

    if isinstance(private, dict) and private and isinstance(graded, dict) and graded:
        _render_assessment_result(private, graded)
    elif isinstance(private, dict) and private and st.session_state.get(
        "student_assessment_started"
    ):
        _render_assessment_questions(private, profile)
    elif isinstance(private, dict) and private:
        _render_assessment_start(private)
    else:
        _render_assessment_chooser(profile)

    st.divider()
    _render_assessment_history(profile)


def _render_assessment_chooser(profile: dict[str, Any]) -> None:
    options = _assessment_skill_options(profile)
    if not options:
        st.info(
            "Add a few skills to your profile (or open a gig with required skills), then "
            "come back here to practise them."
        )
        return

    skill = st.selectbox(
        "Choose a skill to practise", options, key="student_assessment_skill_choice"
    )
    st.caption(
        f"You will get {assessments.MIN_QUESTIONS}-{assessments.MAX_QUESTIONS} "
        "multiple-choice questions. Generating uses the AI model; grading happens "
        "locally in Python."
    )
    if st.button(
        "Generate practice assessment", type="primary", key="student_assessment_generate"
    ):
        _generate_assessment(skill)


def _generate_assessment(skill: Any) -> None:
    """Ask the model for questions, then validate them before anything is shown."""
    context_gig = _gig_for_skill(skill)
    try:
        generated = gigsie_ai.generate_assessment(skill, context_gig)
    except gigsie_ai.GigsieAIError as error:
        # No fabricated fallback questions - show the real reason and stop.
        st.session_state["student_assessment_error"] = (
            f"The practice assessment could not be generated ({error}) "
            "No assessment was created - please try again."
        )
        st.rerun()
        return

    raw = generated.get("assessment") if isinstance(generated, dict) else None
    prepared = assessments.prepare_assessment(raw, skill)
    findings = assessments.validate_assessment(prepared)
    if assessments.has_errors(findings):
        st.session_state["student_assessment_error"] = (
            "The generated questions were not usable, so no assessment was created. "
            "Please try again."
        )
        st.rerun()
        return

    st.session_state["student_assessment_private"] = prepared
    st.session_state["student_assessment_started"] = False
    st.session_state["student_assessment_started_at"] = ""
    st.session_state["student_assessment_graded"] = None
    st.session_state["student_assessment_error"] = None
    st.rerun()


def _render_assessment_start(private: dict[str, Any]) -> None:
    skill = private.get("skill") or "this skill"
    count = assessments.question_count(private)
    st.success(f"Practice assessment ready for **{skill}**.")
    st.caption(
        f"{count} multiple-choice questions. You will see your score and explanations "
        "after you submit."
    )
    st.caption(assessments.SCORING_NOTE)

    col_start, col_other = st.columns(2)
    with col_start:
        if st.button(
            "Start assessment",
            type="primary",
            use_container_width=True,
            key="student_assessment_start",
        ):
            st.session_state["student_assessment_started"] = True
            st.session_state["student_assessment_started_at"] = storage.now_iso()
            st.rerun()
    with col_other:
        if st.button(
            "Choose a different skill",
            use_container_width=True,
            key="student_assessment_discard",
        ):
            _reset_assessment()
            st.rerun()


def _render_assessment_questions(private: dict[str, Any], profile: dict[str, Any]) -> None:
    # Only the public copy is ever rendered - the answer key stays in the private
    # assessment held in session state.
    public = assessments.public_assessment(private)
    assessment_id = private.get("id")

    st.markdown(f"### Practice: {public.get('skill') or 'Skill'}")
    st.caption(
        "Answer what you can. Blank questions are allowed - they are simply counted as "
        "incorrect."
    )

    for number, question in enumerate(public.get("questions") or [], start=1):
        st.markdown(f"**{number}. {question.get('question') or ''}**")
        options = question.get("options") or []
        st.radio(
            f"Answer to question {number}",
            options=list(range(len(options))),
            format_func=lambda index, choices=options: choices[index],
            index=None,
            key=f"student_answer_{assessment_id}_{question.get('id')}",
            label_visibility="collapsed",
        )

    if st.button(
        "Submit answers",
        type="primary",
        key=f"student_assessment_submit_{assessment_id}",
    ):
        _grade_current_assessment(private, profile)


def _collect_answers(private: dict[str, Any]) -> dict[str, Any]:
    assessment_id = private.get("id")
    answers: dict[str, Any] = {}
    for question in private.get("questions") or []:
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("id") or "")
        value = st.session_state.get(f"student_answer_{assessment_id}_{question_id}")
        if value is not None:
            answers[question_id] = value
    return answers


def _grade_current_assessment(private: dict[str, Any], profile: dict[str, Any]) -> None:
    """Validate, grade in Python, and save - at most once per submission."""
    # Guard against a rerun trying to grade the same paper twice.
    existing = st.session_state.get("student_assessment_graded")
    if isinstance(existing, dict) and existing.get("assessment_id") == private.get("id"):
        return

    answers = _collect_answers(private)

    findings = assessments.validate_answers(private, answers)
    if assessments.has_errors(findings):
        for finding in findings:
            if finding.get("level") == "error":
                st.error(finding["message"])
        st.caption("Nothing was graded. Fix the answers above and submit again.")
        return

    grade_result = assessments.grade(private, answers)
    result = assessments.build_result(
        private.get("skill"),
        profile.get("id"),
        private,
        grade_result,
        started_at=_started_datetime(),
        answers=answers,
    )

    try:
        saved = assessments.save_result(result)
    except storage.StorageError as error:
        # Never claim success when the write failed.
        st.error(f"The result could not be saved, so it was not recorded: {error}")
        return

    st.session_state["student_assessment_graded"] = saved
    st.session_state["student_assessment_started"] = False
    st.rerun()


def _render_assessment_result(private: dict[str, Any], record: dict[str, Any]) -> None:
    skill = record.get("skill") or private.get("skill") or "Skill"
    st.markdown(f"##### Practice result: {skill}")
    st.metric(
        "Score",
        f"{record.get('score')} / {record.get('max_score')}",
        f"{record.get('percent')}%",
    )
    st.markdown(f"**{assessments.score_label(record.get('percent'))}**")
    if record.get("unanswered"):
        st.caption(
            f"You left {record.get('unanswered')} question(s) blank; those were counted "
            "as incorrect."
        )
    st.caption(assessments.SCORING_NOTE)
    st.caption(assessments.DISCLAIMER)

    st.markdown("**Review**")
    _render_assessment_review(record.get("review") or [], use_expanders=True)

    st.caption("This result is saved below and in your assessment history.")

    if st.button(
        "Take another assessment",
        type="primary",
        key="student_assessment_again",
    ):
        _reset_assessment()
        st.rerun()


def _render_review_body(item: dict[str, Any]) -> None:
    st.markdown(f"**{item.get('question') or ''}**")
    for index, option in enumerate(item.get("options") or []):
        tags = []
        if index == item.get("correct_index"):
            tags.append("correct answer")
        if index == item.get("selected_index"):
            tags.append("your choice")
        suffix = f"  _({', '.join(tags)})_" if tags else ""
        st.markdown(f"- {option}{suffix}")
    explanation = str(item.get("explanation") or "").strip()
    if explanation:
        st.caption(f"Why: {explanation}")


def _render_assessment_review(review: Any, use_expanders: bool = False) -> None:
    if not isinstance(review, list) or not review:
        st.caption("No per-question detail was stored.")
        return
    for number, item in enumerate(review, start=1):
        if not isinstance(item, dict):
            continue
        if item.get("is_correct"):
            status = "Correct"
        elif not item.get("answered"):
            status = "Not answered"
        else:
            status = "Incorrect"
        if use_expanders:
            with st.expander(f"Question {number} — {status}"):
                _render_review_body(item)
        else:
            st.markdown(f"**Question {number} — {status}**")
            _render_review_body(item)


def _render_assessment_history(profile: dict[str, Any]) -> None:
    st.markdown("##### Assessment history")
    try:
        history = assessments.results_for_profile(profile.get("id"))
    except storage.StorageError as error:
        st.error(f"Your assessment results could not be read: {error}")
        return

    if not history:
        st.caption("No practice results saved yet. Generate an assessment above to begin.")
        return

    st.caption(
        f"{len(history)} practice result(s) saved for this profile. These are practice "
        "scores, not certifications."
    )
    for record in reversed(history):
        skill = record.get("skill") or "Unknown skill"
        with st.container(border=True):
            st.markdown(
                f"**{skill}** — {record.get('score')}/{record.get('max_score')} "
                f"({record.get('percent')}%) · {assessments.score_label(record.get('percent'))}"
            )
            st.caption(
                f"Completed {record.get('completed_at') or record.get('created_at') or 'unknown time'}"
            )
            with st.expander("Review answers and explanations"):
                _render_assessment_review(record.get("review") or [], use_expanders=False)


# ---------------------------------------------------------------------------
# Interviews
# ---------------------------------------------------------------------------
INTERVIEW_FLASH_KEY = "student_interview_flash"


def _set_interview_flash(level: str, message: str) -> None:
    st.session_state[INTERVIEW_FLASH_KEY] = {"level": level, "message": message}


def _do_interview_response(
    interview: dict[str, Any],
    profile: dict[str, Any],
    action: str,
    alternative: str = "",
    success: str = "",
) -> None:
    """Send a student response through the backend, then show the result.

    The profile id is passed so the backend can refuse to answer an interview
    that belongs to a different local profile.
    """
    try:
        interviews.respond_to_interview(
            interview.get("id"),
            action,
            alternative,
            profile_id=profile.get("id"),
        )
    except WorkflowError as error:
        _set_interview_flash("error", f"That did not work: {error}")
    except storage.StorageError as error:
        _set_interview_flash("error", f"Your response could not be saved: {error}")
    else:
        _set_interview_flash("success", success)
    st.rerun()


def _render_interview_response_controls(
    interview: dict[str, Any], profile: dict[str, Any]
) -> None:
    interview_id = interview.get("id")
    col_accept, col_decline = st.columns(2)
    with col_accept:
        if st.button(
            "Accept this time",
            type="primary",
            key=f"stu_accept_{interview_id}",
            use_container_width=True,
        ):
            _do_interview_response(
                interview,
                profile,
                "accept",
                success=(
                    "You accepted this time. Waiting for the business to confirm the "
                    "final details."
                ),
            )
    with col_decline:
        if st.button(
            "Decline",
            key=f"stu_decline_{interview_id}",
            use_container_width=True,
        ):
            _do_interview_response(
                interview,
                profile,
                "decline",
                success="You declined this interview request.",
            )

    st.markdown("**Or propose another time**")
    alternative = st.text_input(
        "Alternative date and time (YYYY-MM-DD HH:MM)",
        key=f"stu_alt_{interview_id}",
        placeholder="2026-10-25 14:30",
    )
    if st.button(
        "Propose this time",
        key=f"stu_alt_btn_{interview_id}",
        use_container_width=True,
    ):
        _do_interview_response(
            interview,
            profile,
            "propose_alternative",
            alternative=alternative,
            success="Your alternative time was sent to the business.",
        )


def _render_student_interview_card(
    interview: dict[str, Any], profile: dict[str, Any]
) -> None:
    status = interview.get("status")
    with st.container(border=True):
        st.markdown(f"**{interview.get('gig_title') or 'Untitled gig'}**")
        st.markdown(
            ui_common.status_pill(status, interviews.INTERVIEW_STATUS_LABELS.get(status, status)),
            unsafe_allow_html=True,
        )
        st.caption(f"Business proposed: {interview.get('requested_datetime') or '—'}")
        if interview.get("alternative_datetime"):
            st.caption(f"Your proposed time: {interview.get('alternative_datetime')}")
        if interview.get("confirmed_datetime"):
            st.caption(f"Confirmed time: {interview.get('confirmed_datetime')}")
        if interview.get("meeting_url"):
            st.caption(f"Meeting link: {interview.get('meeting_url')}")
        else:
            st.caption("No meeting link was provided.")

        if status == interviews.INTERVIEW_REQUESTED:
            _render_interview_response_controls(interview, profile)
        elif status == interviews.INTERVIEW_ACCEPTED:
            st.info("You accepted this time. Waiting for the business to confirm it.")
        elif status == interviews.INTERVIEW_ALTERNATIVE_PROPOSED:
            st.info(
                "You proposed another time. Waiting for the business to confirm or decline it."
            )
        elif status == interviews.INTERVIEW_CONFIRMED:
            st.success("This interview is confirmed. The details above are final.")
        elif status == interviews.INTERVIEW_DECLINED:
            st.caption("This interview was declined, so it is closed.")


def render_interviews_tab() -> None:
    ui_common.section_heading(
        "Interviews",
        "Only the stored status - no video calls, emails, or calendar invites.",
    )
    st.info(
        "Interview coordination here is only the **stored status**: the two sides agree "
        "on a time (and optionally a meeting link). Gigsie does **not** host video calls, "
        "send emails or calendar invites, or provide messaging. This is **local "
        "demonstration data** with no verified accounts."
    )

    profile = _active_profile()
    flash = st.session_state.pop(INTERVIEW_FLASH_KEY, None)
    if isinstance(flash, dict):
        level = flash.get("level")
        message = str(flash.get("message") or "")
        if level == "error":
            st.error(message)
        elif level == "warning":
            st.warning(message)
        elif message:
            st.success(message)

    if not profile:
        st.info(
            "Create or load a profile first - interview requests are linked to your "
            "local profile."
        )
        return

    st.caption(f"All times use this device's local time ({interviews.local_timezone_label()}).")

    try:
        mine = interviews.interviews_for_profile(profile.get("id"))
    except storage.StorageError as error:
        st.error(f"Your interviews could not be read: {error}")
        return

    if not mine:
        st.info(
            "No interview requests yet. When a business requests an interview for one of "
            "your applications, it will appear here. You never need an assessment or an "
            "interview to apply for a gig."
        )
        return

    st.caption(f"{len(mine)} interview(s) linked to this profile.")
    for interview in reversed(mine):
        _render_student_interview_card(interview, profile)


def _student_overview(profile: dict[str, Any] | None) -> None:
    """A compact, honest dashboard shown above the student sections.

    Every figure comes from locally saved data. It deliberately uses cards rather
    than metrics, so a missing value is never dressed up as a score.
    """
    available: int | str = "—"
    try:
        available = len(storage.load_gigs())
    except storage.StorageError:
        available = "—"

    submitted: int | str = "—"
    pending: int | str = "—"
    latest: dict[str, Any] | None = None
    if profile:
        try:
            submitted = len(applications.applications_for_profile(profile.get("id")))
        except storage.StorageError:
            submitted = "—"
        try:
            mine = interviews.interviews_for_profile(profile.get("id"))
            pending = sum(
                1
                for interview in mine
                if interview.get("status")
                in (
                    interviews.INTERVIEW_REQUESTED,
                    interviews.INTERVIEW_ALTERNATIVE_PROPOSED,
                )
            )
        except storage.StorageError:
            pending = "—"
        try:
            results = assessments.results_for_profile(profile.get("id"))
            latest = results[-1] if results else None
        except storage.StorageError:
            latest = None

    columns = st.columns(4)
    with columns[0]:
        ui_common.stat_card("Gigs available", str(available), "Published and sample gigs")
    with columns[1]:
        ui_common.stat_card(
            "Your applications", str(submitted), "Submitted from this profile", tone="info"
        )
    with columns[2]:
        ui_common.stat_card(
            "Interviews to answer", str(pending), "Requests needing your reply", tone="warn"
        )
    with columns[3]:
        if latest:
            ui_common.stat_card(
                "Latest practice",
                f"{latest.get('score')}/{latest.get('max_score')}",
                f"{latest.get('skill') or 'Skill'} · {latest.get('percent')}%",
            )
        else:
            ui_common.stat_card("Latest practice", "—", "No practice results saved yet")

    left, middle, right = st.columns([1, 1.1, 1], gap="medium")
    with left:
        if profile:
            skills = _as_list(profile.get("skills"))
            ui_common.module_card(
                f"Hello, {str(profile.get('display_name') or 'student')}",
                "Skills are self-reported",
                body="",
                tags=(
                    ui_common.skill_tags(skills[:5])
                    if skills
                    else ui_common.chip("No skills listed yet", "warn")
                ),
                fill=True,
            )
        else:
            ui_common.module_card(
                "Start with a profile",
                "Required before you can apply",
                body="",
                tags=ui_common.tags(["Name", "Skills", "Availability"]),
                fill=True,
            )
        if st.button(
            "Open profile",
            key="student_overview_profile",
            use_container_width=True,
        ):
            ui_common.go(ui_common.VIEW_STUDENT, ui_common.SEC_PROFILE)

    with middle:
        _matched_opportunities_card(profile)

    with right:
        _student_activity_card(profile, latest)


def _matched_opportunities_card(profile: dict[str, Any] | None) -> None:
    """Real, deterministically ranked gigs - no invented matches."""
    try:
        gigs = storage.load_gigs()
    except storage.StorageError:
        gigs = []

    if not gigs:
        ui_common.module_card(
            "AI-matched opportunities",
            "No gigs saved yet",
            body="<p>Nothing has been published on this device.</p>",
            fill=True,
        )
        return

    ranked = _order_gigs(gigs, profile)[:3]
    rows = []
    for gig in ranked:
        match = validation.match_gig_to_skills(gig, profile or {})
        detail = (
            f"Skill match {match['score']}%"
            if match["score"] is not None
            else "No score - add skills to your profile"
        )
        rows.append(
            "<div>"
            f"<b>{_escape(ui_common.gig_title(gig))} {ui_common.gig_badge(gig)}</b>"
            f'<div class="muted">{_escape(ui_common.gig_budget(gig))} · {_escape(detail)}</div>'
            "</div>"
        )
    ui_common.module_card(
        "AI-matched opportunities",
        f"{len(gigs)} gig(s) on this device",
        body=ui_common.list_rows(rows),
        tags=ui_common.tags(["Deterministic", "No invented scores"]),
        fill=True,
    )
    if st.button("Open Find Work", key="student_overview_find", use_container_width=True):
        ui_common.go(ui_common.VIEW_STUDENT, ui_common.SEC_FIND_WORK)


def _student_activity_card(
    profile: dict[str, Any] | None, latest: dict[str, Any] | None
) -> None:
    """Applications, interviews, and practice - all read from local storage."""
    if not profile:
        ui_common.module_card(
            "Your activity",
            "Needs a profile",
            body="<p>Applications and interviews appear here once a profile is active.</p>",
            fill=True,
        )
        if st.button(
            "Create a profile",
            key="student_activity_profile",
            use_container_width=True,
        ):
            ui_common.go(ui_common.VIEW_STUDENT, ui_common.SEC_PROFILE)
        return

    rows: list[str] = []
    try:
        mine = applications.applications_for_profile(profile.get("id"))
    except storage.StorageError:
        mine = []
    for application in list(reversed(mine))[:3]:
        rows.append(
            "<div>"
            f"<b>{_escape(str(application.get('gig_title') or 'Untitled gig'))}</b>"
            f'<div class="muted">Submitted {application.get("created_at") or "—"}</div></div>'
            f"<div>{ui_common.status_pill(application.get('status'))}</div>"
        )

    try:
        my_interviews = interviews.interviews_for_profile(profile.get("id"))
    except storage.StorageError:
        my_interviews = []
    notes = [
        f"{len(my_interviews)} interview request(s)" if my_interviews else "No interviews yet",
        (
            f"Practice: {latest.get('skill')} {latest.get('score')}/{latest.get('max_score')}"
            if latest
            else "No practice results yet"
        ),
    ]
    ui_common.module_card(
        "Your activity",
        "Applications, interviews, practice",
        body="".join(
            [ui_common.list_rows(rows)] + [f"<p>{note}</p>" for note in notes]
        ),
        tags=ui_common.tags(["Practice, not certification"]),
        fill=True,
    )
    if st.button(
        "My applications",
        key="student_activity_applications",
        use_container_width=True,
    ):
        ui_common.go(ui_common.VIEW_STUDENT, ui_common.SEC_APPLICATIONS)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
_SECTION_RENDERERS = {
    ui_common.SEC_PROFILE: render_profile_tab,
    ui_common.SEC_FIND_WORK: render_browse_tab,
    ui_common.SEC_APPLICATIONS: render_my_applications_tab,
    ui_common.SEC_ASSESSMENTS: render_assessments_tab,
    ui_common.SEC_INTERVIEWS: render_interviews_tab,
}


def render_student(section: str = "") -> None:
    """Render the student area.

    The sidebar is the only navigation. Each student destination is its own page,
    so there is no second tab bar inside the page.
    """
    ui_common.inject_styles()
    _student_header(section or ui_common.SEC_STUDENT_HOME)

    if section and section in _SECTION_RENDERERS:
        ui_common.page_header(
            ui_common.SECTION_LABEL.get(section, "Student"),
            _SECTION_SUBTITLES.get(section, ""),
            eyebrow_text="Student",
        )
        _SECTION_RENDERERS[section]()
        return

    ui_common.page_header(
        "Student Overview",
        "Find work, read the agreed scope, and apply.",
        eyebrow_text="For students",
    )
    _student_overview(_active_profile())
    _student_next_steps()


def _student_next_steps() -> None:
    """Real next actions from the Overview, so nothing important is hidden."""
    profile = _active_profile()
    columns = st.columns(3, gap="medium")
    with columns[0]:
        if st.button(
            "Find Work", type="primary", use_container_width=True, key="ov_find_work"
        ):
            ui_common.go(ui_common.VIEW_STUDENT, ui_common.SEC_FIND_WORK)
    with columns[1]:
        if st.button(
            "Open My Profile", use_container_width=True, key="ov_profile"
        ):
            ui_common.go(ui_common.VIEW_STUDENT, ui_common.SEC_PROFILE)
    with columns[2]:
        if st.button(
            "My Applications", use_container_width=True, key="ov_applications"
        ):
            ui_common.go(ui_common.VIEW_STUDENT, ui_common.SEC_APPLICATIONS)

    if not profile:
        st.caption(
            "Create a profile first - matches and applications are linked to it."
        )


_SECTION_SUBTITLES = {
    ui_common.SEC_PROFILE: "Self-reported. Saved on this device only.",
    ui_common.SEC_FIND_WORK: "Published gigs matched against your real skills.",
    ui_common.SEC_APPLICATIONS: "Your proposals and their stored status.",
    ui_common.SEC_ASSESSMENTS: "AI practice questions, graded in Python.",
    ui_common.SEC_INTERVIEWS: "Stored interview status only.",
}
