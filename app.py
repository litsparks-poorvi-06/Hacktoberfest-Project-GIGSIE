"""Gigsie - Streamlit interface.

This file is the *presentation* layer only. The real work lives elsewhere:

    * gigsie_ai.py    - drafts the brief with Groq (the model never decides facts)
    * validation.py   - deterministic checks on inputs, profiles, and matching
    * fairscope.py    - deterministic scope review and the Gig Passport
    * storage.py      - saves and loads gigs, profiles, and applications from JSON
    * gig_workflow.py - business form validation, record building, safe publishing
    * profiles.py     - student profiles (local prototype, no accounts)
    * applications.py - student proposals: validation, dedupe, status transitions
    * student_ui.py   - the student area: profile, browse gigs, and apply

The business journey is one coherent flow:

    1. Describe the business task.
    2. Generate the actual AI task brief.
    3. Review deterministic clarity checks and separately labelled AI suggestions.
    4. Compare Budget-first, Outcome-first, and Milestone-first strategies.
    5. Review and edit the proposed changes.
    6. Approve the Gig Passport.
    7. Explicitly publish the gig.

Run locally with:
    streamlit run app.py
"""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from gigsie_ai import GigsieAIError, generate_task_brief
from gig_workflow import (
    PublishError,
    join_lines,
    publish_once,
    split_lines,
    validate_form,
)
from business_ui import render_business_interviews
from student_ui import render_student
import fairscope
import storage
import ui_common

TAGLINE = ui_common.TAGLINE
PRODUCT_BLURB = (
    "Gigsie helps a small business turn a vague request into a clear, realistic "
    "freelance task. The AI drafts the brief, Python checks its scope, and you decide "
    "what gets published. Students then discover the gig, read the same agreed scope, "
    "and apply."
)

# The steps shown in the business progress rail.
_BUSINESS_STEPS = ["Describe the task", "Draft the brief", "Review the scope", "Publish"]
_STUDENT_STEPS = ["Profile", "Browse gigs", "Apply", "Assess & interview"]

# Session keys that make up a single draft, cleared together by "Start a new brief".
DRAFT_KEYS = [
    "request",
    "brief_result",
    "scope_variant",
    "draft_key",
    "published_record",
    "published_draft_key",
]


# ---------------------------------------------------------------------------
# Entry point and shared state
# ---------------------------------------------------------------------------
def _inject_styles() -> None:
    """Kept for backwards compatibility; the design system lives in ui_common."""
    ui_common.inject_styles()


def _init_state() -> None:
    if "view" not in st.session_state:
        st.session_state["view"] = ui_common.VIEW_HOME
    for key in DRAFT_KEYS:
        if key not in st.session_state:
            st.session_state[key] = None
    if "draft_revision" not in st.session_state:
        st.session_state["draft_revision"] = 0


def _go(view: str) -> None:
    st.session_state["view"] = view
    st.rerun()


def _reset_draft() -> None:
    """Forget the current draft so a fresh one can start."""
    for key in DRAFT_KEYS:
        st.session_state[key] = None
    st.session_state["draft_revision"] = (st.session_state.get("draft_revision") or 0) + 1
    st.rerun()


# ---------------------------------------------------------------------------
# Landing
# ---------------------------------------------------------------------------
def render_landing() -> None:
    ui_common.hero()
    st.markdown(f'<p class="gs-lead">{PRODUCT_BLURB}</p>', unsafe_allow_html=True)

    st.markdown("#### Choose how you want to start")
    col_business, col_student = st.columns(2, gap="large")

    with col_business:
        ui_common.eyebrow("For businesses")
        st.markdown(
            """
            <div class="gs-card gs-card--brand">
                <h3>🏪 Post a clear gig</h3>
                <p>Describe a task in plain words. Gigsie drafts a structured brief,
                reviews its scope, and helps you publish it as a gig students can trust.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            "Start a business request",
            type="primary",
            use_container_width=True,
            key="landing_business",
        ):
            _go("business")

    with col_student:
        ui_common.eyebrow("For students")
        st.markdown(
            """
            <div class="gs-card gs-card--accent">
                <h3>🎓 Find work that fits</h3>
                <p>Browse gigs that match your skills, read the agreed scope in the "
                "Gig Passport, and apply with a clear proposal.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            "Enter the student area",
            use_container_width=True,
            key="landing_student",
        ):
            _go("student")

    st.divider()
    st.markdown("#### How Gigsie works")
    col_1, col_2, col_3, col_4 = st.columns(4)
    with col_1:
        st.markdown(
            '<div class="gs-card"><h4>1 · Describe</h4><p>The business explains the '
            "work and the outcome it wants.</p></div>",
            unsafe_allow_html=True,
        )
    with col_2:
        st.markdown(
            '<div class="gs-card"><h4>2 · Draft</h4><p>The AI drafts scope, skills, '
            "and open questions as an editable brief.</p></div>",
            unsafe_allow_html=True,
        )
    with col_3:
        st.markdown(
            '<div class="gs-card"><h4>3 · Review</h4><p>FairScope adds deterministic '
            "checks, kept separate from the AI's suggestions.</p></div>",
            unsafe_allow_html=True,
        )
    with col_4:
        st.markdown(
            '<div class="gs-card"><h4>4 · Publish</h4><p>The approved Gig Passport is '
            "saved so students read the same scope.</p></div>",
            unsafe_allow_html=True,
        )

    st.caption(
        "Gigsie is a prototype that connects small businesses with students and "
        "beginner freelancers. There are no accounts, payments, or ratings yet."
    )


def _top_bar() -> None:
    """Back-to-home control shared by the business and student areas."""
    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Back to start", key="back_to_landing"):
            _go("landing")


# ---------------------------------------------------------------------------
# Business flow
# ---------------------------------------------------------------------------
def render_business() -> None:
    _top_bar()

    if st.session_state.get("brief_result") is None:
        ui_common.step_rail(_BUSINESS_STEPS, 0)
        st.markdown("### 🏪 Describe the business task")
        st.caption(
            "Write the task in everyday language. Gigsie drafts a brief you review and "
            "edit before publishing. Required fields are marked with *."
        )
        _render_request_form()
    else:
        ui_common.step_rail(_BUSINESS_STEPS, 1)
        _render_brief_editor(st.session_state["brief_result"])

    st.divider()
    _render_saved_gigs()

    st.divider()
    render_business_interviews()


def _render_request_form() -> None:
    with st.form("request_form"):
        st.markdown("##### Tell Gigsie about the work")
        project_name = st.text_input(
            "Business or project name (optional)",
            placeholder="e.g. Sunrise Bakery",
        )
        description = st.text_area(
            "What work needs to be done? *",
            placeholder="e.g. I want help promoting my new seasonal menu on Instagram.",
            height=100,
        )
        outcome = st.text_area(
            "What outcome do you want? *",
            placeholder="e.g. More local customers see the menu and visit the shop.",
            height=100,
        )

        col_budget, col_deadline = st.columns(2)
        with col_budget:
            budget = st.number_input(
                "Budget in INR *",
                min_value=0.0,
                step=100.0,
                value=0.0,
                format="%.0f",
                help="Your budget in Indian rupees. Enter a positive amount.",
            )
        with col_deadline:
            deadline = st.text_input(
                "Deadline or completion time *",
                placeholder="e.g. 2 days, or 15 Oct 2026",
            )

        extra_context = st.text_area(
            "Additional context (optional)",
            placeholder="e.g. Target audience, platforms you already use, brand colours.",
            height=80,
        )

        submitted = st.form_submit_button(
            "Generate task brief", type="primary", use_container_width=True
        )

    if not submitted:
        return

    request = {
        "project_name": project_name.strip(),
        "description": description.strip(),
        "outcome": outcome.strip(),
        "budget": budget,
        "deadline": deadline.strip(),
        "extra_context": extra_context.strip(),
    }

    errors = [f for f in validate_form(request) if f.get("level") == "error"]
    if errors:
        st.error("Please fix the following before generating a brief:")
        for finding in errors:
            st.markdown(f"- {finding.get('message')}")
        return

    _generate_brief(request)


def _generate_brief(request: dict) -> None:
    with st.spinner("Drafting a scope-aware brief with the AI model..."):
        try:
            result = generate_task_brief(request)
        except GigsieAIError as error:
            st.error(f"The brief was not generated. {error}")
            return

    if not result or not result.get("brief"):
        st.error("The brief was not generated. Please try again.")
        return

    st.session_state["request"] = request
    st.session_state["brief_result"] = result
    st.session_state["scope_variant"] = None
    st.session_state["draft_key"] = str(uuid4())
    st.session_state["published_record"] = None
    st.session_state["published_draft_key"] = None
    st.session_state["draft_revision"] = (st.session_state.get("draft_revision") or 0) + 1
    st.rerun()


def _render_brief_editor(result: dict) -> None:
    request = st.session_state.get("request") or {}
    brief = result.get("brief") or {}
    revision = st.session_state.get("draft_revision") or 0

    ui_common.eyebrow("Draft ready")
    st.markdown("### Review and edit the task brief")
    st.success("Draft ready. Review and edit anything before you publish.")

    metric_left, metric_right = st.columns(2)
    metric_left.metric("Stated budget (INR)", f"{float(request.get('budget') or 0):,.0f}")
    metric_right.metric("Stated deadline", request.get("deadline") or "Not provided")

    # FairScope: deterministic clarity checks and scope signals for this draft.
    _render_fairscope_panel(request, brief)

    # Optional, explicit scope strategies. Nothing changes without a decision.
    _render_strategy_section(request, brief)

    # The Gig Passport is built from the current draft. It is only ever saved by
    # publishing - never automatically.
    passport = fairscope.build_passport(brief, request)

    with st.form("brief_editor"):
        st.markdown("#### Edit the brief")
        st.caption(
            "These fields become the published gig. Nothing below is confirmed until "
            "you edit it and publish."
        )
        title = st.text_input("Title", value=brief.get("title", ""), key=f"brief_title_{revision}")
        objective = st.text_area(
            "Objective", value=brief.get("objective", ""), height=90, key=f"brief_objective_{revision}"
        )
        deliverables = st.text_area(
            "Deliverables (one per line)",
            value=join_lines(brief.get("deliverables")),
            height=120,
            key=f"brief_deliverables_{revision}",
        )
        required_skills = st.text_area(
            "Required skills (one per line)",
            value=join_lines(brief.get("required_skills")),
            height=100,
            key=f"brief_skills_{revision}",
        )
        acceptance_criteria = st.text_area(
            "Acceptance criteria (one per line)",
            value=join_lines(brief.get("acceptance_criteria")),
            height=120,
            key=f"brief_criteria_{revision}",
        )

        st.divider()
        st.caption(
            "The AI's suggestions below are shown for context only. **You have not "
            "confirmed them**, and they are not edited here."
        )
        st.markdown("**Clarifying questions (from the AI)**")
        _bullet_list(list(brief.get("clarifying_questions") or []))
        st.markdown("**Assumptions (from the AI)**")
        _bullet_list(list(brief.get("assumptions") or []))
        st.markdown("**Feasibility warnings (from the AI)**")
        _bullet_list(list(brief.get("warnings") or []))

        st.divider()
        st.markdown("**Automatic checks**")
        _show_findings(list(result.get("validation") or []))

        st.divider()
        passport_values, acknowledged = _render_passport_editor(passport, revision)

        already_published = st.session_state.get("published_record") is not None
        publish_clicked = st.form_submit_button(
            "Publish gig",
            type="primary",
            use_container_width=True,
            disabled=already_published,
        )

    edited_brief = {
        "title": title.strip(),
        "objective": objective.strip(),
        "deliverables": split_lines(deliverables),
        "required_skills": split_lines(required_skills),
        "acceptance_criteria": split_lines(acceptance_criteria),
        # Kept as context; not editable and never presented as confirmed.
        "clarifying_questions": list(brief.get("clarifying_questions") or []),
        "assumptions": list(brief.get("assumptions") or []),
        "warnings": list(brief.get("warnings") or []),
    }
    # Carry the FairScope-only fields through from the passport editor.
    for key, value in passport_values.items():
        edited_brief[key] = value

    # Rebuild the passport from the EDITED brief, then apply the owner's edits and
    # any explicit acknowledgements.
    edited_passport = fairscope.build_passport(edited_brief, request)
    edited_passport = fairscope.update_passport_values(edited_passport, passport_values)
    edited_passport = fairscope.acknowledge(edited_passport, acknowledged)
    if result.get("scope_strategy"):
        edited_passport["strategy"] = result["scope_strategy"]

    if publish_clicked:
        _handle_publish(edited_brief, request, edited_passport)

    published = st.session_state.get("published_record")
    if published:
        st.success(f"Published. This gig is saved with ID **{published.get('id')}**.")
        st.caption(
            "It is stored through storage.py (data/gigs.json), with its Gig Passport, "
            "and will be available to the student side."
        )

    if st.button("Start a new brief", key="new_brief"):
        _reset_draft()


# ---------------------------------------------------------------------------
# FairScope panel: clarity checks, scope signals, AI notes, next action
# ---------------------------------------------------------------------------
def _render_fairscope_panel(request: dict, brief: dict) -> None:
    analysis = fairscope.analyze_brief(request, brief)
    checks = analysis.get("clarity", {}).get("checks", [])
    signals = analysis.get("signals") or []
    ai = analysis.get("ai_suggestions") or {}
    action = analysis.get("next_action") or {}

    with st.container(border=True):
        st.markdown("#### 🔍 FairScope review")
        st.caption(
            "**The AI drafts. Python checks. The business decides.** The **Python "
            "checks** below are **deterministic**, and they stay separate from the "
            "AI's own suggestions. FairScope never judges whether a budget is fair."
        )

        st.markdown("**Clarity check**")
        icons = {
            fairscope.STATUS_OK: "✅",
            fairscope.STATUS_NEEDS: "⚠️",
            fairscope.STATUS_MISSING: "⛔",
        }
        for check in checks:
            icon = icons.get(check.get("status"), "•")
            st.markdown(
                '<div class="gs-check">'
                f'<div class="gs-check-icon">{icon}</div>'
                '<div class="gs-check-body">'
                f'<div class="gs-check-label">{check.get("label")}</div>'
                f'<div class="gs-check-detail">{check.get("detail")}</div>'
                "</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown("**Scope signals (deterministic)**")
        if signals:
            _show_findings(signals)
        else:
            st.caption("No scope signals were detected.")

        st.markdown("**AI suggestions (from the model - not verified)**")
        suggestions_shown = False
        for label, key in (
            ("Warnings", "warnings"),
            ("Assumptions", "assumptions"),
            ("Open questions", "questions"),
        ):
            items = list(ai.get(key) or [])
            if items:
                suggestions_shown = True
                st.markdown(f"*{label}:*")
                _bullet_list(items)
        if not suggestions_shown:
            st.caption("The model added no extra notes.")

        st.markdown("**Recommended next action**")
        if action.get("summary"):
            st.info(action["summary"])
        for step in action.get("steps") or []:
            st.markdown(f"- {step}")


# ---------------------------------------------------------------------------
# Scope strategies: explicit, comparable, never applied automatically
# ---------------------------------------------------------------------------
def _render_strategy_section(request: dict, brief: dict) -> None:
    with st.container(border=True):
        st.markdown("#### 🧭 Scope strategies")
        st.caption(
            "Generate an alternative approach to compare with your current draft. "
            "This asks the AI once, only when you click. Nothing is replaced or "
            "published automatically."
        )

        options = [fairscope.strategy_meta(key)["label"] for key in fairscope.SCOPE_STRATEGY_KEYS]
        choice = st.selectbox("Choose a strategy", options, key="strategy_choice")
        key = fairscope.SCOPE_STRATEGY_KEYS[options.index(choice)]
        st.caption(fairscope.strategy_meta(key)["blurb"])

        if st.button("Generate this strategy version", key="strategy_generate"):
            _generate_strategy_variant(request, brief, key)

        variant = st.session_state.get("scope_variant")
        if isinstance(variant, dict):
            _render_strategy_comparison(brief, variant, request)


def _render_strategy_comparison(current: dict, variant: dict, request: dict) -> None:
    proposed = variant.get("brief") or {}
    label = fairscope.strategy_label(variant.get("strategy"))

    st.divider()
    st.markdown(f"**Proposed: {label}**")
    st.caption(
        "This is only a proposal. Your current draft is unchanged until you choose it."
    )

    left, right = st.columns(2)
    with left:
        st.markdown("##### Your current draft")
        st.markdown(f"**Objective:** {current.get('objective') or '_(none)_'}")
        st.markdown("**Deliverables**")
        _bullet_list(list(current.get("deliverables") or []))
    with right:
        st.markdown("##### Proposed version")
        st.markdown(f"**Objective:** {proposed.get('objective') or '_(none)_'}")
        st.markdown("**Deliverables**")
        _bullet_list(list(proposed.get("deliverables") or []))

    st.markdown("**What changed**")
    changes = _brief_changes(current, proposed)
    if changes:
        _bullet_list(changes)
    else:
        st.caption("No field-level differences could be detected.")

    col_use, col_discard = st.columns(2)
    with col_use:
        if st.button(
            "Use this proposed version as my draft",
            type="primary",
            use_container_width=True,
            key="strategy_use",
        ):
            _apply_strategy_variant(variant)
    with col_discard:
        if st.button(
            "Discard proposed version",
            use_container_width=True,
            key="strategy_discard",
        ):
            st.session_state["scope_variant"] = None
            st.rerun()


def _brief_changes(current: dict, proposed: dict) -> list[str]:
    """Return short, human-readable differences between two briefs."""
    changes: list[str] = []
    comparable = ["title", "objective", "deliverables", "required_skills", "acceptance_criteria"]
    for key in comparable:
        before = current.get(key)
        after = proposed.get(key)
        if isinstance(before, list) or isinstance(after, list):
            b = [str(item) for item in (before or [])]
            a = [str(item) for item in (after or [])]
            if b != a:
                changes.append(f"{key.replace('_', ' ').title()}: {len(b)} to {len(a)} item(s)")
        elif str(before or "").strip() != str(after or "").strip():
            changes.append(f"{key.replace('_', ' ').title()} was revised.")
    for key in ("exclusions", "client_responsibilities", "revision_expectations"):
        if key in proposed:
            changes.append(f"Added {key.replace('_', ' ')}: {len(proposed.get(key) or [])} item(s)")
    return changes


def _apply_strategy_variant(variant: dict) -> None:
    """Replace the current draft with the chosen strategy version, explicitly."""
    result = dict(st.session_state.get("brief_result") or {})
    result["brief"] = variant.get("brief") or {}
    result["validation"] = variant.get("validation") or []
    result["problems"] = variant.get("problems") or []
    if variant.get("strategy"):
        result["scope_strategy"] = variant["strategy"]
    st.session_state["brief_result"] = result
    st.session_state["scope_variant"] = None
    st.session_state["draft_key"] = str(uuid4())
    st.session_state["published_record"] = None
    st.session_state["published_draft_key"] = None
    st.session_state["draft_revision"] = (st.session_state.get("draft_revision") or 0) + 1
    st.rerun()


def _generate_strategy_variant(request: dict, brief: dict, strategy_key: str) -> None:
    label = fairscope.strategy_label(strategy_key)
    with st.spinner(f"Generating the {label} version..."):
        try:
            variant = generate_task_brief(
                request, scope_strategy=strategy_key, current_brief=brief
            )
        except GigsieAIError as error:
            st.error(
                f"The {label} version was not generated, so your current draft is "
                f"unchanged. {error}"
            )
            return

    if not variant or not variant.get("brief"):
        st.error(
            f"The {label} version was not generated, so your current draft is "
            "unchanged. Please try again."
        )
        return

    st.session_state["scope_variant"] = variant
    st.rerun()


# ---------------------------------------------------------------------------
# Gig Passport editor
# ---------------------------------------------------------------------------
def _render_passport_value(section: dict) -> None:
    ui_common.passport_value(section)


def _render_passport_editor(passport: dict, revision: int = 0) -> tuple[dict, list[str]]:
    """Render the editable Gig Passport inside the editor form.

    Returns ``(values, acknowledged)``. Values holds the passport-only fields the
    owner edited; acknowledged lists the essential sections the owner explicitly
    accepted as "not yet specified".

    ``revision`` is folded into the widget keys so that applying a different draft
    (for example a strategy version) re-initialises the fields from the new values
    instead of keeping stale ones.
    """
    sections = passport.get("sections") or {}
    values: dict = {}
    acknowledged: list = []

    st.markdown("#### 🛂 Gig Passport")
    st.caption(
        "The agreed scope. It is saved with the gig and shown to students. Sections "
        "taken from your draft appear here; anything still unknown is marked "
        "**Needs clarification** and is never invented."
    )

    grouped = [
        (
            "Confirmed from your draft",
            ("objective", "deliverables", "definition_of_done", "included_work", "required_skills"),
        ),
        ("Boundaries", ("exclusions", "client_responsibilities", "revision_expectations")),
        ("Context and open points", ("open_questions", "assumptions", "scope_warnings")),
        ("Budget and deadline", ("budget", "deadline")),
    ]

    editable = {
        "exclusions": "Exclusions (one per line)",
        "client_responsibilities": "Client responsibilities (one per line)",
        "revision_expectations": "Revision expectations (one per line)",
    }

    for heading, keys in grouped:
        present = [key for key in keys if key in sections]
        if not present:
            continue
        st.markdown(f"**{heading}**")
        for key in present:
            section = sections.get(key) or {}
            st.markdown(f"*{section.get('label', key)}*")
            if key in editable:
                value = st.text_area(
                    editable[key],
                    value=join_lines(section.get("value")),
                    height=80,
                    key=f"passport_{key}_{revision}",
                    label_visibility="collapsed",
                )
                values[key] = split_lines(value)
            else:
                ui_common.passport_value(section)

    # Explicit acknowledgement for essential gaps that are still missing.
    gaps = [
        key
        for key, section in sections.items()
        if section.get("essential") and section.get("needs_clarification")
    ]
    if gaps:
        st.warning(
            "Some essential details are still missing. Fill them in above, or "
            "explicitly acknowledge them as not yet specified before publishing."
        )
        for key in gaps:
            section = sections.get(key) or {}
            if st.checkbox(
                f"Acknowledge '{section.get('label', key)}' as not yet specified",
                key=f"ack_{key}_{revision}",
            ):
                acknowledged.append(key)

    return values, acknowledged


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------
def _handle_publish(brief: dict, request: dict, passport: dict | None = None) -> None:
    """Publish through the workflow layer; only report success after it is saved."""
    draft_key = st.session_state.get("draft_key")
    try:
        record = publish_once(
            st.session_state,
            draft_key,
            brief,
            request,
            passport=passport,
        )
    except PublishError as error:
        st.error(f"The gig was not published. {error}")
        return

    if record is None:
        st.info("This draft has already been published.")
        return

    st.session_state["published_record"] = record
    # A fresh draft key so a later edit + publish is treated as a new gig.
    st.session_state["draft_key"] = str(uuid4())


# ---------------------------------------------------------------------------
# Saved gigs (business view)
# ---------------------------------------------------------------------------
def _render_saved_gigs() -> None:
    st.markdown("#### 📁 Saved gigs")
    try:
        gigs = storage.load_gigs()
    except storage.StorageError as error:
        st.error(f"Saved gigs could not be read: {error}")
        return

    published = [gig for gig in gigs if not gig.get("sample")]
    samples = [gig for gig in gigs if gig.get("sample")]

    st.caption(f"{len(published)} published · {len(samples)} labelled sample gig(s)")

    if published:
        for gig in published:
            title = gig.get("title") or "Untitled gig"
            status = gig.get("status") or "open"
            st.markdown(f"- **{title}** · ID `{gig.get('id')}` · status: {status}")
    else:
        st.caption("Nothing published yet. Published gigs will appear here.")

    if samples:
        with st.expander(f"Sample gigs ({len(samples)})"):
            st.caption(
                "Labelled examples that ship with Gigsie. They are **not** real "
                "businesses or real requests."
            )
            for gig in samples:
                title = gig.get("title") or "Untitled gig"
                st.markdown(
                    f"- {title} " + ui_common.sample_tag(), unsafe_allow_html=True
                )


# ---------------------------------------------------------------------------
# Small local helpers
# ---------------------------------------------------------------------------
def _bullet_list(items: list) -> None:
    values = [str(item) for item in items if str(item).strip()]
    if not values:
        st.caption("None.")
        return
    for item in values:
        st.markdown(f"- {item}")


def _show_findings(findings: list) -> None:
    if not findings:
        st.caption("No issues detected.")
        return
    for finding in findings:
        level = finding.get("level")
        message = finding.get("message", "")
        if level == "error":
            st.error(message)
        elif level == "warning":
            st.warning(message)
        else:
            st.info(message)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(
        page_title="Gigsie Scope Studio",
        page_icon="🧩",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_styles()
    _init_state()

    # Make labelled sample gigs available through the same storage the student
    # side reads. A failure here must not stop the app working.
    try:
        storage.seed_samples_on_first_run()
    except storage.StorageError:
        pass

    ui_common.nav_sidebar()

    view = st.session_state.get("view", ui_common.VIEW_HOME)
    if view == ui_common.VIEW_BUSINESS:
        render_business()
    elif view == ui_common.VIEW_STUDENT:
        render_student()
    else:
        render_landing()


if __name__ == "__main__":
    main()
