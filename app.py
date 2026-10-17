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
    * ui_common.py    - the design system, navigation shell, and shared cards

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

from html import escape as _escape
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
import applications
import fairscope
import interviews
import storage
import ui_common
import voice_narration

TAGLINE = ui_common.TAGLINE
PRODUCT_BLURB = (
    "Gigsie helps a small business turn a vague request into a clear, achievable "
    "freelance gig. The AI drafts the brief, Python checks its scope, and the business "
    "decides what gets published. Students then discover the gig, read the same agreed "
    "scope, and apply."
)

# The visible progress through the Create-with-AI workspace.
_BUSINESS_STEPS = [
    "Describe the task",
    "Generate the draft",
    "Review FairScope",
    "Compare strategies",
    "Edit the Gig Passport",
    "Publish the gig",
]

# Session keys that make up a single draft, cleared together by "Start a new brief".
DRAFT_KEYS = [
    "request",
    "brief_result",
    "scope_variant",
    "scope_variant_key",
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
    if "section" not in st.session_state:
        st.session_state["section"] = ui_common.SEC_OVERVIEW
    for key in DRAFT_KEYS:
        if key not in st.session_state:
            st.session_state[key] = None
    if "draft_revision" not in st.session_state:
        st.session_state["draft_revision"] = 0


def _go(view: str, section: str = ui_common.SEC_OVERVIEW) -> None:
    st.session_state["view"] = view
    st.session_state["section"] = section
    st.rerun()


def _reset_draft() -> None:
    """Forget the current draft so a fresh one can start."""
    for key in DRAFT_KEYS:
        st.session_state[key] = None
    st.session_state["draft_revision"] = (st.session_state.get("draft_revision") or 0) + 1
    st.rerun()


# ---------------------------------------------------------------------------
# Real local data for every dashboard panel
# ---------------------------------------------------------------------------
def _home_budget(gig: dict) -> str:
    """Readable budget for the cards; never guesses a number."""
    return ui_common.gig_budget(gig)


def _snapshot() -> dict:
    """Everything the dashboards read, in one guarded pass.

    Every figure comes from local storage. A read failure is reported honestly
    instead of being hidden behind a zero.
    """
    snapshot: dict = {
        "gigs": [],
        "published": [],
        "samples": [],
        "applications": [],
        "interviews": [],
        "pending_interviews": [],
        "recent": [],
        "error": None,
    }
    try:
        snapshot["gigs"] = storage.load_gigs()
    except storage.StorageError as error:
        snapshot["error"] = str(error)
        return snapshot

    snapshot["published"] = [gig for gig in snapshot["gigs"] if not gig.get("sample")]
    snapshot["samples"] = [gig for gig in snapshot["gigs"] if gig.get("sample")]
    snapshot["recent"] = list(reversed(snapshot["published"]))[:4]

    try:
        snapshot["applications"] = applications.all_applications()
    except storage.StorageError:
        snapshot["applications"] = []
    try:
        loaded = storage.load_interviews()
    except storage.StorageError:
        loaded = []
    snapshot["interviews"] = loaded
    snapshot["pending_interviews"] = [
        interview
        for interview in loaded
        if interview.get("status") in interviews.PENDING_BUSINESS_STATUSES
    ]
    return snapshot


def _home_snapshot() -> dict:
    """Backwards-compatible wrapper around :func:`_snapshot`."""
    return _snapshot()


def _gigs_by_id(snapshot: dict) -> dict:
    return {gig.get("id"): gig for gig in snapshot["gigs"] if gig.get("id")}


def _linked_applications(snapshot: dict) -> list[dict]:
    """Applications whose gig really exists locally - nothing is invented."""
    known = _gigs_by_id(snapshot)
    return [
        application
        for application in snapshot["applications"]
        if application.get("gig_id") in known
    ]


# ---------------------------------------------------------------------------
# Overview (the app home)
# ---------------------------------------------------------------------------
def _profile_chip() -> tuple[str, str]:
    """The real local student profile, if one is loaded."""
    profile = st.session_state.get("student_profile")
    if isinstance(profile, dict) and profile.get("id"):
        name = str(profile.get("display_name") or "Unnamed student")
        return name, f"Student profile · {profile.get('id')}"
    return "", ""


def render_landing() -> None:
    """Overview: a real dashboard of what is saved on this device."""
    name, sub = _profile_chip()
    ui_common.top_header(
        crumb=["Workspace", "Overview"],
        role=ui_common.ROLE_BUSINESS,
        search=True,
        search_key="gs_search",
        search_placeholder="Search your gigs",
        profile_name=name,
        profile_sub=sub,
        primary_label="Create a gig with AI",
        primary_target=(ui_common.VIEW_BUSINESS, ui_common.SEC_CREATE),
    )

    ui_common.eyebrow("Local-first prototype")
    ui_common.display_title("Overview", "of this workspace")
    st.markdown(
        f'<p class="gs-page-sub">{_escape(ui_common.TAGLINE)}</p>',
        unsafe_allow_html=True,
    )

    snapshot = _snapshot()
    if snapshot["error"]:
        st.error(f"Saved gigs could not be read: {snapshot['error']}")

    # --- The two real entry points ---------------------------------------
    left, right = st.columns(2, gap="medium")
    with left:
        ui_common.panel(
            "For businesses",
            "Turn a vague request into a clear gig",
            body="",
            footer=ui_common.tags(["AI draft", "FairScope", "Publish"]),
            fill=True,
        )
        if st.button(
            "Start a business request",
            type="primary",
            use_container_width=True,
            key="landing_business",
        ):
            _go(ui_common.VIEW_BUSINESS)
    with right:
        ui_common.panel(
            "For students",
            "Find work that matches your skills",
            body="",
            footer=ui_common.tags(["Profile", "Apply", "Practice"]),
            accent="alt",
            fill=True,
        )
        if st.button(
            "Enter the student area",
            use_container_width=True,
            key="landing_student",
        ):
            _go(ui_common.VIEW_STUDENT, ui_common.SEC_STUDENT_HOME)

    # --- Metric tiles -----------------------------------------------------
    linked = _linked_applications(snapshot)
    metrics = st.columns(4, gap="medium")
    with metrics[0]:
        ui_common.stat_card("Published gigs", str(len(snapshot["published"])), "Visible to students")
    with metrics[1]:
        ui_common.stat_card("Applications", str(len(linked)), "Against your gigs", tone="info")
    with metrics[2]:
        ui_common.stat_card(
            "Awaiting a reply",
            str(len(snapshot["pending_interviews"])),
            "Interview requests",
            tone="warn",
        )
    with metrics[3]:
        ui_common.stat_card("Sample gigs", str(len(snapshot["samples"])), "Labelled examples")

    # --- Three panel columns ----------------------------------------------
    main_col, mid_col, side_col = st.columns([1.3, 1, 1], gap="medium")
    with main_col:
        _overview_gigs_panel(snapshot)
    with mid_col:
        _overview_workflow_panel()
    with side_col:
        _needs_attention_panel(snapshot, linked)

    # --- Pending applications, only when real data exists -------------------
    if linked:
        ui_common.header_rule()
        ui_common.section_heading(
            "Pending applications", "Real proposals against gigs saved on this device."
        )
        _pending_applications_panel(snapshot, linked)

    # --- Saved gigs table (filtered by the header search) ------------------
    ui_common.header_rule()
    ui_common.section_heading(
        "Your workspace", "Every record saved on this device, newest first."
    )
    _overview_table(snapshot)


def _pending_applications_panel(snapshot: dict, linked: list[dict]) -> None:
    """A compact row per real application, with its actual status."""
    rows = []
    for application in linked[:6]:
        rows.append(
            "<div>"
            f"<b>{_escape(str(application.get('student_name') or 'Unnamed student'))}</b>"
            f'<div class="muted">{_escape(str(application.get("gig_title") or "Untitled gig"))}'
            f" · {_escape(str(application.get('created_at') or ''))}</div></div>"
            f"<div>{ui_common.status_pill(application.get('status'))}</div>"
        )
    ui_common.panel(
        f"{len(linked)} application(s) across your gigs",
        f"{len(snapshot['pending_interviews'])} interview request(s) awaiting a reply",
        body=ui_common.list_rows(rows),
        footer=ui_common.tags(["Local demonstration data"]),
    )
    if st.button(
        "Review applicants", key="overview_applicants", use_container_width=True
    ):
        _go(ui_common.VIEW_BUSINESS, ui_common.SEC_APPLICANTS)


def _render_applicants_page() -> None:
    """Applicants and interviews, grouped by the gig they belong to."""
    _business_header(
        "Applicants & Interviews",
        primary_label="Published Gigs",
        primary_target=(ui_common.VIEW_BUSINESS, ui_common.SEC_PUBLISHED),
    )
    ui_common.page_header(
        "Applicants & Interviews",
        "Real applications and interview requests against gigs saved on this device.",
        eyebrow_text="Business · Applicants & Interviews",
    )

    snapshot = _snapshot()
    if snapshot["error"]:
        st.error(f"Saved gigs could not be read: {snapshot['error']}")
        return
    linked = _linked_applications(snapshot)

    tiles = st.columns(3, gap="medium")
    with tiles[0]:
        ui_common.stat_card("Applications", str(len(linked)), "Against your gigs")
    with tiles[1]:
        ui_common.stat_card(
            "Awaiting a reply",
            str(len(snapshot["pending_interviews"])),
            "Interview requests",
            tone="warn",
        )
    with tiles[2]:
        waiting = [
            application
            for application in linked
            if application.get("status")
            in (applications.STATUS_SUBMITTED, applications.STATUS_SHORTLISTED)
        ]
        ui_common.stat_card(
            "No decision yet", str(len(waiting)), "Not shortlisted or rejected", tone="info"
        )

    ui_common.header_rule()
    render_business_interviews()


def _overview_gigs_panel(snapshot: dict) -> None:
    """Left column: the real gigs saved locally."""
    if not snapshot["published"]:
        ui_common.panel(
            "Your Gigs",
            "Nothing published yet",
            body="<p>Describe a task, review the scope, then publish. Your first "
            "gig appears here and in the student listing.</p>",
            footer=ui_common.tags(["Draft", "Review", "Publish"]),
            fill=True,
        )
        if st.button(
            "Create a gig with AI", key="overview_empty_create", use_container_width=True
        ):
            _go(ui_common.VIEW_BUSINESS, ui_common.SEC_CREATE)
        return

    recent = snapshot["recent"]
    ui_common.panel(
        "Your Gigs",
        f"{len(snapshot['published'])} published on this device",
        body=ui_common.list_rows([ui_common.gig_row(gig) for gig in recent]),
        footer=ui_common.tags(ui_common.gig_skills(recent[0]), limit=3),
        fill=True,
    )
    if st.button("Open Published Gigs", key="overview_open_published", use_container_width=True):
        _go(ui_common.VIEW_BUSINESS, ui_common.SEC_PUBLISHED)


def _overview_workflow_panel() -> None:
    """Centre column: how a gig becomes clear, plus the one real next action."""
    ui_common.module_card(
        "How a gig becomes clear",
        "Six steps, you stay in control",
        body=ui_common.bullets(
            [
                "Describe the work",
                "AI drafts the brief",
                "FairScope checks it",
                "You approve and publish",
            ]
        ),
        tags=ui_common.tags(["Groq", "gpt-oss-20b"]),
        fill=True,
    )
    if st.button("Create a gig with AI", key="overview_create", use_container_width=True):
        _go(ui_common.VIEW_BUSINESS, ui_common.SEC_CREATE)


def _overview_table(snapshot: dict) -> None:
    """A compact table of the real saved gigs, filtered by the header search."""
    gigs = list(reversed(snapshot["published"])) + list(snapshot["samples"])
    if not gigs:
        ui_common.empty_state(
            "▤",
            "Nothing saved on this device yet",
            "Publish a gig and it will show up here with its budget, deadline, and status.",
        )
        return

    query = str(st.session_state.get("gs_search") or "").strip().lower()
    if query:
        gigs = [
            gig
            for gig in gigs
            if query in ui_common.gig_title(gig).lower()
            or query in ui_common.gig_context(gig).lower()
            or any(query in skill.lower() for skill in ui_common.gig_skills(gig))
        ]
        if not gigs:
            ui_common.empty_state(
                "⌕",
                "No saved gig matches that search",
                "Try a title, a business name, or a skill such as Canva.",
            )
            return
        st.caption(f"{len(gigs)} saved gig(s) match '{query}'.")

    rows = []
    for gig in gigs:
        rows.append(
            [
                f"<b>{_escape(ui_common.gig_title(gig))}</b>"
                + (f" {ui_common.sample_tag()}" if gig.get("sample") else ""),
                _escape(ui_common.gig_context(gig)),
                ui_common.status_pill(
                    "sample" if gig.get("sample") else gig.get("status", "open"),
                    "Sample" if gig.get("sample") else str(gig.get("status", "open")).title(),
                ),
                _escape(ui_common.gig_budget(gig)),
                _escape(ui_common.gig_deadline(gig)),
                f'<span class="muted">{_escape(str(gig.get("id") or ""))}</span>',
            ]
        )
    ui_common.data_table(
        ["Gig", "Business", "Status", "Budget", "Deadline", "ID"], rows
    )


def _top_bar() -> None:
    """Kept for compatibility: the back control now lives in the page header."""
    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Back to start", key="back_to_landing"):
            _go(ui_common.VIEW_HOME)


# ---------------------------------------------------------------------------
# Business workspace
# ---------------------------------------------------------------------------
def render_business(section: str = "") -> None:
    """The business side. ``section`` is one of the sidebar destinations.

    Each workflow gets its own page, so no page is a single long column:
    create a request -> FairScope review -> Gig Passport -> publish.
    """
    if section == ui_common.SEC_PASSPORT:
        _render_passport_page()
        return
    if section == ui_common.SEC_PUBLISHED:
        _render_published_page()
        return
    if section == ui_common.SEC_APPLICANTS:
        _render_applicants_page()
        return
    _render_create_page()


def _business_header(
    crumb: str,
    *,
    primary_label: str = "",
    primary_target: tuple[str, str] | None = None,
    search: bool = False,
    search_placeholder: str = "",
) -> None:
    """One header shape for every business page."""
    status_name, status_sub, status_avatar = _business_status()
    ui_common.top_header(
        crumb=["Business", crumb],
        role=ui_common.ROLE_BUSINESS,
        back_key="back_to_landing",
        search=search,
        search_key="gs_search",
        search_placeholder=search_placeholder or "Search saved gigs",
        profile_name=status_name,
        profile_sub=status_sub,
        profile_avatar=status_avatar,
        primary_label=primary_label,
        primary_target=primary_target,
    )


def _business_status() -> tuple[str, str]:
    """Real local status for the header: the active student profile, if any."""
    profile = st.session_state.get("student_profile")
    if isinstance(profile, dict) and profile.get("id"):
        return (
            str(profile.get("display_name") or "Unnamed student"),
            f"Student profile · {profile.get('id')}",
            "",
        )
    snapshot = _snapshot()
    if snapshot["error"]:
        return "Storage problem", "Saved gigs could not be read", "!"
    return (
        f"{len(snapshot['published'])} published gig(s)",
        "Business view · this device",
        "◆",
    )


def _needs_attention_panel(snapshot: dict, linked: list[dict]) -> None:
    """Only real, unresolved items ever appear here."""
    pending = snapshot["pending_interviews"]
    waiting = [
        application
        for application in linked
        if application.get("status")
        in (applications.STATUS_SUBMITTED, applications.STATUS_SHORTLISTED)
    ]

    if not pending and not waiting and st.session_state.get("brief_result") is None:
        ui_common.module_card(
            "Needs attention",
            "Nothing outstanding",
            body="<p>No interview request and no unreviewed application.</p>",
            tags=ui_common.tags(["Clear"]),
            fill=True,
        )
        if st.button(
            "Review applicants",
            key="attention_empty_applicants",
            use_container_width=True,
        ):
            _go(ui_common.VIEW_BUSINESS, ui_common.SEC_APPLICANTS)
        return

    rows: list[str] = []
    for interview in pending[:3]:
        rows.append(
            "<div>"
            f"<b>{_escape(str(interview.get('student_name') or 'Unnamed student'))}</b>"
            f'<div class="muted">{_escape(str(interview.get("requested_datetime") or "no time"))}'
            "</div></div>"
            f"<div>{ui_common.status_pill(interview.get('status'), 'Needs reply')}</div>"
        )
    notes: list[str] = []
    if waiting:
        notes.append(f"{len(waiting)} application(s) with no decision yet")
    if st.session_state.get("brief_result") is not None and not st.session_state.get(
        "published_record"
    ):
        notes.append("A generated brief is waiting to be published")
    ui_common.module_card(
        "Needs attention",
        f"{len(pending)} interview request(s)",
        body="".join(
            [ui_common.list_rows(rows)] + [f"<p>{note}</p>" for note in notes]
        ),
        tags=ui_common.tags(["Real items only"]),
        fill=True,
    )
    if st.button(
        "Review applicants",
        key="attention_applicants",
        use_container_width=True,
    ):
        _go(ui_common.VIEW_BUSINESS, ui_common.SEC_APPLICANTS)


# ---------------------------------------------------------------------------
# Create with AI, then the FairScope review
# ---------------------------------------------------------------------------
def _create_active_step() -> int:
    """Where the owner is in the create workflow, derived from real state."""
    if st.session_state.get("brief_result") is None:
        return 0
    if st.session_state.get("published_record") is not None:
        return 5
    if st.session_state.get("scope_variant") is not None:
        return 3
    return 2


def _render_create_page() -> None:
    """The request form, or the FairScope review once a draft exists."""
    has_draft = st.session_state.get("brief_result") is not None

    _business_header(
        "Create with AI",
        primary_label="Review the Gig Passport" if has_draft else "See published gigs",
        primary_target=(
            (ui_common.VIEW_BUSINESS, ui_common.SEC_PASSPORT)
            if has_draft
            else (ui_common.VIEW_BUSINESS, ui_common.SEC_PUBLISHED)
        ),
    )
    ui_common.page_header(
        "FairScope review" if has_draft else "Create a gig with AI",
        "Review the scope Gigsie produced, then approve a Gig Passport."
        if has_draft
        else "Describe the work in your own words.",
        eyebrow_text="Business · Create with AI",
    )
    ui_common.step_rail(_BUSINESS_STEPS, _create_active_step())

    if not has_draft:
        ui_common.section_heading(
            "Tell us what you need", "Required fields are marked with *."
        )
        _render_request_form()
        return

    _render_fairscope_review(st.session_state["brief_result"])


def _render_fairscope_review(result: dict) -> None:
    """A focused review screen: request, draft, checks, signals, strategies.

    The editable Gig Passport and publishing live on their own page, so this
    screen is about reviewing the scope rather than editing everything at once.
    """
    request = st.session_state.get("request") or {}
    brief = result.get("brief") or {}
    analysis = fairscope.analyze_brief(request, brief)

    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        # The whole request lives inside one card, so this column is a single
        # element and matches the draft card beside it exactly.
        request_pairs: list[tuple[str, str]] = []
        if request.get("description"):
            request_pairs.append(("What you need", str(request["description"])))
        if request.get("outcome"):
            request_pairs.append(("Outcome you want", str(request["outcome"])))
        if request.get("extra_context"):
            request_pairs.append(("Extra context", str(request["extra_context"])))
        request_pairs.append(
            ("Budget (INR)", f"{float(request.get('budget') or 0):,.0f}")
        )
        request_pairs.append(
            ("Deadline", str(request.get("deadline") or "Not provided"))
        )
        ui_common.panel(
            "Your original request",
            "Exactly as you wrote it",
            body=ui_common.key_values(request_pairs),
            footer=ui_common.tags(["Never changed by Gigsie"]),
            fill=True,
        )

    with right:
        draft_pairs: list[tuple[str, str]] = [
            ("Title", ui_common.gig_title(brief)),
            ("Objective", str(brief.get("objective") or "Not written yet")),
        ]
        # key_values escapes its values, so the deliverables list is appended as
        # markup rather than passed through it.
        body = ui_common.key_values(draft_pairs)
        deliverables = list(brief.get("deliverables") or [])
        if deliverables:
            body += (
                '<div class="gs-note-h">Deliverables</div>'
                + ui_common.bullets(deliverables)
            )
        ui_common.panel(
            "The AI draft",
            "A proposal, not a decision",
            body=body,
            footer=ui_common.tags(ui_common.gig_skills(brief), limit=6),
            fill=True,
        )

    ui_common.header_rule()
    _render_fairscope_panel(request, brief)
    _render_strategy_section(request, brief)

    ui_common.header_rule()
    left_btn, right_note = st.columns([1, 1.6], gap="medium", vertical_alignment="center")
    with left_btn:
        if st.button(
            "Continue to the Gig Passport",
            type="primary",
            use_container_width=True,
            key="continue_to_passport",
        ):
            _go(ui_common.VIEW_BUSINESS, ui_common.SEC_PASSPORT)
    with right_note:
        ui_common.voice_brief(
            label="Listen to FairScope",
            text=voice_narration.build_fairscope_narration(
                brief=brief, request=request, analysis=analysis
            ),
            key="voice_fairscope",
            caption="A spoken summary of the draft above, built from the same fields.",
        )

    if st.button("Start a new brief", key="new_brief"):
        _reset_draft()


def _render_passport_page() -> None:
    """The editable Gig Passport and the explicit publish action."""
    result = st.session_state.get("brief_result")
    if not isinstance(result, dict) or not result.get("brief"):
        _business_header(
            "Gig Passport",
            primary_label="Create with AI",
            primary_target=(ui_common.VIEW_BUSINESS, ui_common.SEC_CREATE),
        )
        ui_common.page_header(
            "Gig Passport",
            "There is no draft to edit yet.",
            eyebrow_text="Business · Gig Passport",
        )
        ui_common.empty_state(
            "🛂",
            "No draft yet",
            "Describe a task in Create with AI and the Gig Passport will be built here.",
        )
        if st.button(
            "Create a gig with AI",
            type="primary",
            use_container_width=True,
            key="passport_go_create",
        ):
            _go(ui_common.VIEW_BUSINESS, ui_common.SEC_CREATE)
        return

    _business_header(
        "Gig Passport",
        primary_label="Back to FairScope",
        primary_target=(ui_common.VIEW_BUSINESS, ui_common.SEC_CREATE),
    )
    ui_common.page_header(
        "Gig Passport",
        "Edit the agreed scope, then publish it explicitly.",
        eyebrow_text="Business · Gig Passport",
    )
    ui_common.step_rail(_BUSINESS_STEPS, 4)
    _render_brief_editor(result)


def _render_published_page() -> None:
    _business_header(
        "Published Gigs",
        search=True,
        search_placeholder="Search published gigs",
        primary_label="Create a gig with AI",
        primary_target=(ui_common.VIEW_BUSINESS, ui_common.SEC_CREATE),
    )
    ui_common.page_header(
        "Published Gigs",
        "Everything published on this device. Samples are listed last.",
        eyebrow_text="Business · Published Gigs",
    )

    snapshot = _snapshot()
    if snapshot["error"]:
        st.error(f"Saved gigs could not be read: {snapshot['error']}")
        return

    columns = st.columns(4)
    with columns[0]:
        ui_common.stat_card("Published", str(len(snapshot["published"])), "Open to students")
    with columns[1]:
        ui_common.stat_card("Sample", str(len(snapshot["samples"])), "Labelled examples")
    with columns[2]:
        ui_common.stat_card(
            "Applications", str(len(_linked_applications(snapshot))), "Against these gigs", tone="info"
        )
    with columns[3]:
        ui_common.stat_card(
            "Interviews",
            str(len(snapshot["pending_interviews"])),
            "Awaiting a reply",
            tone="warn",
        )

    ui_common.header_rule()
    _render_saved_gigs()
    ui_common.header_rule()
    render_business_interviews()


def _render_request_form() -> None:
    with st.form("request_form"):
        st.markdown("##### Tell Gigsie about the work")
        st.caption(
            "Describe the task in everyday words, then give a real budget and deadline. "
            "Example: *I run a bakery and want three Instagram posts for my new menu. "
            "INR 800, needed in 2 days.* Budget and deadline are required so the scope "
            "can be reviewed against them."
        )
        project_name = st.text_input(
            "Business or project name (optional)",
            placeholder="e.g. Sunrise Bakery",
        )
        description = st.text_area(
            "What work needs to be done? *",
            placeholder="e.g. I want help promoting my new seasonal menu on Instagram.",
            height=100,
            help="Plain words are fine. What is the task, and what already exists?",
        )
        outcome = st.text_area(
            "What outcome do you want? *",
            placeholder="e.g. More local customers see the menu and visit the shop.",
            height=100,
            help="What should be different once this work is done?",
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
    st.session_state["scope_variant_key"] = None
    st.session_state["draft_key"] = str(uuid4())
    st.session_state["published_record"] = None
    st.session_state["published_draft_key"] = None
    st.session_state["draft_revision"] = (st.session_state.get("draft_revision") or 0) + 1
    st.rerun()


def _passport_readiness(passport: dict) -> list[tuple[str, str]]:
    """Real publication readiness, computed from the passport itself."""
    sections = passport.get("sections") or {}
    unresolved = [
        label
        for label, section in sections.items()
        if isinstance(section, dict) and section.get("needs_clarification")
    ]
    essential = [
        label
        for label, section in sections.items()
        if isinstance(section, dict)
        and section.get("essential")
        and section.get("needs_clarification")
    ]
    total = len(sections) or 1
    return [
        ("Scope sections", f"{total - len(unresolved)} of {total} specified"),
        (
            "Still needs clarification",
            ", ".join(str(item).replace("_", " ") for item in unresolved) or "None",
        ),
        (
            "Must be acknowledged",
            ", ".join(str(item).replace("_", " ") for item in essential) or "None",
        ),
    ]


def _render_brief_editor(result: dict) -> None:
    """The editable Gig Passport: a spacious form with an explicit publish."""
    request = st.session_state.get("request") or {}
    brief = result.get("brief") or {}
    revision = st.session_state.get("draft_revision") or 0

    # The Gig Passport is built from the current draft. It is only ever saved by
    # publishing - never automatically.
    passport = fairscope.build_passport(brief, request)

    summary_left, summary_right = st.columns([1.3, 1], gap="medium")
    with summary_left:
        ui_common.panel(
            "Agreed scope",
            "Built from your draft; edit anything below",
            body=ui_common.key_values(
                [
                    ("Title", ui_common.gig_title(brief)),
                    ("Budget (INR)", f"{float(request.get('budget') or 0):,.0f}"),
                    ("Deadline", str(request.get("deadline") or "Not provided")),
                ]
            ),
            footer=ui_common.tags(ui_common.gig_skills(brief), limit=6),
            fill=True,
        )
    with summary_right:
        ui_common.panel(
            "Before you publish",
            "Resolve, or acknowledge what is still missing",
            body=ui_common.key_values(_passport_readiness(passport)),
            footer=ui_common.tags(["Nothing publishes silently"]),
            fill=True,
        )

    # The narration sits on its own row so it never disturbs the card heights.
    ui_common.section_heading(
        "Listen to this Gig Passport",
        "A short spoken summary of exactly the scope a student would read. "
        "Generated only when you ask for it.",
    )
    ui_common.voice_brief(
        label="Listen to this Gig Passport",
        text=voice_narration.build_passport_narration(
            gig=st.session_state.get("published_record") or brief,
            passport=passport,
        ),
        key="voice_passport",
        caption="Built from this passport only - nothing is added.",
    )

    ui_common.header_rule()
    with st.form("brief_editor"):
        st.markdown("#### Edit the brief and the Gig Passport")
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

        with st.expander("AI suggestions (context only - not confirmed)", expanded=False):
            st.caption(
                "The model's own notes. **You have not confirmed them**, and they are "
                "not edited here."
            )
            st.markdown("**Clarifying questions**")
            _bullet_list(list(brief.get("clarifying_questions") or []))
            st.markdown("**Assumptions**")
            _bullet_list(list(brief.get("assumptions") or []))
            st.markdown("**Feasibility warnings**")
            _bullet_list(list(brief.get("warnings") or []))

        with st.expander("Automatic checks", expanded=False):
            _show_findings(list(result.get("validation") or []))

        ui_common.header_rule()
        st.markdown("#### Gig Passport sections")
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

    left, right = st.columns([1.15, 1], gap="medium")

    # Deterministic checks on the left, in one card.
    icons = {
        fairscope.STATUS_OK: "✅",
        fairscope.STATUS_NEEDS: "⚠️",
        fairscope.STATUS_MISSING: "⛔",
    }
    check_rows = "".join(
        '<div class="gs-check">'
        f'<div class="gs-check-icon">{icons.get(check.get("status"), "•")}</div>'
        '<div class="gs-check-body">'
        f'<div class="gs-check-label">{_escape(str(check.get("label")))}</div>'
        f'<div class="gs-check-detail">{_escape(str(check.get("detail")))}</div>'
        "</div></div>"
        for check in checks
    )
    with left:
        ui_common.panel(
            "Clarity check",
            "The AI drafts. Python checks. You decide.",
            body=check_rows or "<p>No checks were produced.</p>",
            footer=ui_common.tags(["Deterministic", f"{len(checks)} check(s)"]),
            fill=True,
        )

    # Deterministic signals above the model's own notes, clearly separated.
    with right:
        signal_rows = "".join(
            f'<div class="gs-signal gs-signal--{_escape(str(f.get("level") or "info"))}">'
            f'{_escape(str(f.get("message") or ""))}</div>'
            for f in signals
        )
        ui_common.panel(
            "Scope signals",
            "Deterministic",
            body=signal_rows or "<p>No scope signals were detected.</p>",
            fill=True,
        )

        notes: list[str] = []
        for label, key in (
            ("Warnings", "warnings"),
            ("Assumptions", "assumptions"),
            ("Open questions", "questions"),
        ):
            items = [str(item) for item in (ai.get(key) or []) if str(item).strip()]
            if items:
                notes.append(
                    f'<div class="gs-note-h">{_escape(label)}</div>' + ui_common.bullets(items)
                )
        ui_common.panel(
            "AI suggestions",
            "From the model · not verified",
            body="".join(notes) or "<p>The model added no extra notes.</p>",
            fill=True,
        )

    # The recommended next action spans the width: it is the decision, not a detail.
    if action.get("summary") or action.get("steps"):
        steps = list(action.get("steps") or [])
        ui_common.panel(
            "Recommended next action",
            "One clear next step, from Python",
            body="<p>"
            + _escape(str(action.get("summary") or ""))
            + "</p>"
            + (ui_common.bullets(steps) if steps else ""),
            footer=ui_common.tags(["Not a judgement on your budget"]),
        )


# ---------------------------------------------------------------------------
# Scope strategies: explicit, comparable, never applied automatically
# ---------------------------------------------------------------------------
def _render_strategy_section(request: dict, brief: dict) -> None:
    ui_common.section_heading(
        "Compare scope strategies",
        "Generates an alternative to compare with your draft. This asks the AI once, "
        "only when you click. Nothing is replaced or published automatically.",
    )

    options = [fairscope.strategy_meta(key)["label"] for key in fairscope.SCOPE_STRATEGY_KEYS]
    col_choice, col_blurb, col_action = st.columns([1.1, 1.6, 1], gap="medium")
    with col_choice:
        choice = st.selectbox("Choose a strategy", options, key="strategy_choice")
    key = fairscope.SCOPE_STRATEGY_KEYS[options.index(choice)]
    with col_blurb:
        st.caption(fairscope.strategy_meta(key)["blurb"])
    with col_action:
        if st.button(
            "Generate this strategy version",
            key="strategy_generate",
            use_container_width=True,
        ):
            _generate_strategy_variant(request, brief, key)

    variant = st.session_state.get("scope_variant")
    if isinstance(variant, dict):
        _render_strategy_comparison(brief, variant, request)


def _variant_strategy(variant: dict) -> str:
    """The strategy key a proposed version belongs to.

    The model response records it as ``scope_strategy``. The key the business
    actually chose is also stored alongside the variant, so the identity
    survives a response that omits it. Returns ``""`` when there is genuinely
    no strategy, so callers never print a fabricated label.
    """
    for candidate in (
        variant.get("scope_strategy"),
        variant.get("strategy"),
        st.session_state.get("scope_variant_key"),
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _render_strategy_comparison(current: dict, variant: dict, request: dict) -> None:
    proposed = variant.get("brief") or {}
    strategy_key = _variant_strategy(variant)
    label = fairscope.strategy_label(strategy_key) if strategy_key else "Proposed version"

    ui_common.panel(
        f"Proposed: {label}",
        "Only a proposal — your current draft is unchanged until you choose it",
        body=ui_common.bullets(
            [
                f"Objective: {proposed.get('objective') or '_(none)_'}",
            ]
        )
        + _strategy_deliverables_block(proposed)
        + "<div class='gs-note-h'>What changed</div>"
        + (ui_common.bullets(_brief_changes(current, proposed))
           if _brief_changes(current, proposed)
           else "<p>No field-level differences could be detected.</p>"),
        footer=ui_common.tags(
            [f"Strategy: {strategy_key}"] if strategy_key else ["Strategy not recorded"]
        ),
    )

    col_use, col_discard = st.columns(2, gap="medium")
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
            _discard_strategy_variant()


def _strategy_deliverables_block(brief: dict) -> str:
    """Deliverables for the comparison panel, as escaped markup."""
    items = [str(item) for item in (brief.get("deliverables") or []) if str(item).strip()]
    if not items:
        return ""
    return "<div class='gs-note-h'>Deliverables</div>" + ui_common.bullets(items)


def _discard_strategy_variant() -> None:
    """Drop the proposal and its strategy identity, keeping the draft intact."""
    st.session_state["scope_variant"] = None
    st.session_state["scope_variant_key"] = None
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
    strategy_key = _variant_strategy(variant)
    if strategy_key:
        result["scope_strategy"] = strategy_key
    st.session_state["brief_result"] = result
    st.session_state["scope_variant"] = None
    st.session_state["scope_variant_key"] = None
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
    # The chosen key is recorded next to the variant so the comparison heading
    # and the accept action always agree with what was actually selected.
    st.session_state["scope_variant_key"] = strategy_key
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
# Published gigs
# ---------------------------------------------------------------------------
def _render_saved_gigs() -> None:
    ui_common.section_heading(
        "Saved gigs",
        "What you publish is stored locally and becomes visible to students.",
    )
    try:
        gigs = storage.load_gigs()
    except storage.StorageError as error:
        st.error(f"Saved gigs could not be read: {error}")
        return

    published = [gig for gig in gigs if not gig.get("sample")]
    samples = [gig for gig in gigs if gig.get("sample")]

    query = str(st.session_state.get("gs_search") or "").strip().lower()
    if query:
        published = [
            gig
            for gig in published
            if query in ui_common.gig_title(gig).lower()
            or query in ui_common.gig_context(gig).lower()
            or any(query in skill.lower() for skill in ui_common.gig_skills(gig))
        ]

    if published:
        st.caption(f"{len(published)} published gig(s) on this device.")
        _gig_grid(published)
    else:
        ui_common.empty_state(
            "▤",
            "Nothing published yet" if not query else "No saved gig matches that search",
            "Published gigs will appear here and in the student listing. Use Create with "
            "AI to publish your first one.",
        )

    if samples:
        with st.expander(f"Sample gigs ({len(samples)}) — labelled examples, not real requests"):
            st.caption(
                "Labelled examples that ship with Gigsie. They are **not** real "
                "businesses or real requests."
            )
            _gig_grid(samples)


def _gig_grid(gigs: list[dict]) -> None:
    """Render saved gigs as equal-height cards, one real row at a time."""
    ui_common.gig_grid([ui_common.gig_card(gig, fill=True) for gig in gigs])


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
        page_title="Gigsie — clear, achievable freelance gigs",
        page_icon="◆",
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

    view = ui_common.current_view()
    section = ui_common.current_section()
    if view == ui_common.VIEW_BUSINESS:
        render_business(section)
    elif view == ui_common.VIEW_STUDENT:
        render_student(section)
    else:
        render_landing()


if __name__ == "__main__":
    main()
