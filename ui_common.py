"""Shared Streamlit presentation helpers for Gigsie.

Kept separate so ``app.py``, ``student_ui.py`` and ``business_ui.py`` all use the
same styling and the same small helpers, without importing each other in a loop.

This module is presentation only. It renders HTML and tiny helpers; every rule
and every write lives in the backend modules. The visual system (colors, type,
spacing, cards, chips, pills) is defined once here so the product feels like one
coherent workspace rather than a set of separate forms.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

TAGLINE = "Turn vague business requests into clear, ready-to-post gigs."
PRODUCT_NAME = "Gigsie Scope Studio"

VIEW_HOME = "landing"
VIEW_BUSINESS = "business"
VIEW_STUDENT = "student"

VIEW_TO_LABEL = {VIEW_HOME: "Home", VIEW_BUSINESS: "Business", VIEW_STUDENT: "Student"}
_VIEW_ICON = {VIEW_HOME: "🏠", VIEW_BUSINESS: "🏪", VIEW_STUDENT: "🎓"}


# ---------------------------------------------------------------------------
# Design system: one stylesheet for the whole product
# ---------------------------------------------------------------------------
_CSS = """
<style>
    :root {
        --gs-ink: #0f172a;
        --gs-ink-soft: #334155;
        --gs-muted: #64748b;
        --gs-line: rgba(100, 116, 139, 0.20);
        --gs-surface: #ffffff;
        --gs-surface-2: #f8fafc;
        --gs-brand: #4f46e5;
        --gs-brand-2: #7c3aed;
        --gs-brand-3: #a855f7;
        --gs-ok: #166534;
        --gs-ok-bg: #dcfce7;
        --gs-warn: #92400e;
        --gs-warn-bg: #fef3c7;
        --gs-stop: #991b1b;
        --gs-stop-bg: #fee2e2;
        --gs-info: #3730a3;
        --gs-info-bg: #e0e7ff;
        --gs-radius: 16px;
        --gs-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
        --gs-shadow-sm: 0 4px 14px rgba(15, 23, 42, 0.06);
    }

    .block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1120px; }

    html, body, [class*="st-"], button, input, textarea, select {
        font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    }

    h1, h2, h3, h4 { color: var(--gs-ink); letter-spacing: -0.01em; }
    h2 { font-weight: 800; }
    h3 { font-weight: 700; }
    a { color: var(--gs-brand); }

    /* --- Hero ---------------------------------------------------------- */
    .gigsie-hero {
        position: relative;
        overflow: hidden;
        background: linear-gradient(135deg, #4338ca 0%, #6d28d9 52%, #9333ea 100%);
        color: #ffffff;
        padding: 2.4rem 2.2rem;
        border-radius: 22px;
        margin-bottom: 1.6rem;
        box-shadow: 0 18px 44px rgba(79, 70, 229, 0.30);
    }
    .gigsie-hero::after {
        content: "";
        position: absolute;
        top: -60px; right: -60px;
        width: 240px; height: 240px;
        background: radial-gradient(circle, rgba(255,255,255,0.20), rgba(255,255,255,0));
        border-radius: 50%;
    }
    .gigsie-hero h1 { margin: 0; font-size: 2.5rem; font-weight: 800; letter-spacing: -0.02em; }
    .gigsie-hero p { margin: 0.65rem 0 0; opacity: 0.95; font-size: 1.08rem; max-width: 44rem; line-height: 1.5; }
    .gigsie-badge {
        display: inline-block;
        background: rgba(255, 255, 255, 0.18);
        border: 1px solid rgba(255, 255, 255, 0.25);
        border-radius: 999px;
        padding: 0.26rem 0.85rem;
        font-size: 0.76rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-top: 1.1rem;
    }

    /* --- Small type helpers ------------------------------------------- */
    .gs-eyebrow {
        text-transform: uppercase;
        letter-spacing: 0.10em;
        font-size: 0.72rem;
        font-weight: 700;
        color: var(--gs-brand);
        margin: 0.2rem 0 0.1rem;
    }
    .gs-lead { color: var(--gs-ink-soft); font-size: 1.02rem; line-height: 1.55; }
    .gs-muted { color: var(--gs-muted); }

    /* --- Cards --------------------------------------------------------- */
    .gs-card {
        border: 1px solid var(--gs-line);
        border-radius: var(--gs-radius);
        background: var(--gs-surface);
        padding: 1.15rem 1.25rem;
        box-shadow: var(--gs-shadow-sm);
        margin-bottom: 0.4rem;
    }
    .gs-card h3, .gs-card h4 { margin: 0 0 0.3rem; }
    .gs-card p { margin: 0.25rem 0 0; color: var(--gs-ink-soft); line-height: 1.5; }
    .gs-card--brand { border-top: 3px solid var(--gs-brand); }
    .gs-card--accent { border-top: 3px solid var(--gs-brand-2); }

    /* Frames around real Streamlit widgets (containers with a border). */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: var(--gs-radius);
        border-color: var(--gs-line);
        box-shadow: var(--gs-shadow-sm);
        background: var(--gs-surface);
        padding: 0.35rem 0.35rem;
    }
    div[data-testid="stForm"] {
        border-radius: var(--gs-radius);
        border: 1px solid var(--gs-line);
        box-shadow: var(--gs-shadow-sm);
        padding: 1.1rem 1.2rem;
    }

    /* --- Chips / tags -------------------------------------------------- */
    .gs-chip {
        display: inline-block;
        border-radius: 999px;
        padding: 0.16rem 0.7rem;
        font-size: 0.76rem;
        font-weight: 600;
        margin: 0.1rem 0.25rem 0.1rem 0;
        border: 1px solid transparent;
    }
    .gs-chip.tone-ok { background: var(--gs-ok-bg); color: var(--gs-ok); }
    .gs-chip.tone-warn { background: var(--gs-warn-bg); color: var(--gs-warn); }
    .gs-chip.tone-stop { background: var(--gs-stop-bg); color: var(--gs-stop); }
    .gs-chip.tone-info { background: var(--gs-info-bg); color: var(--gs-info); }
    .gs-chip.tone-neutral { background: #eef2f7; color: var(--gs-ink-soft); }

    .gigsie-sample-tag {
        display: inline-block;
        background: #fef3c7;
        color: #92400e;
        border-radius: 999px;
        padding: 0.05rem 0.6rem;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        vertical-align: middle;
    }

    /* --- Status pills (applications & interviews) ---------------------- */
    .gigsie-pill {
        display: inline-block;
        border-radius: 999px;
        padding: 0.14rem 0.7rem;
        font-size: 0.75rem;
        font-weight: 700;
        vertical-align: middle;
    }
    .pill-submitted { background: #e0e7ff; color: #3730a3; }
    .pill-shortlisted { background: #dbeafe; color: #1e40af; }
    .pill-interview_requested { background: #fef3c7; color: #92400e; }
    .pill-interview_confirmed { background: #dcfce7; color: #166534; }
    .pill-requested { background: #fef3c7; color: #92400e; }
    .pill-alternative_proposed { background: #ffedd5; color: #9a3412; }
    .pill-confirmed { background: #dcfce7; color: #166534; }
    .pill-declined { background: #fee2e2; color: #991b1b; }
    .pill-accepted { background: #dcfce7; color: #166534; }
    .pill-rejected { background: #fee2e2; color: #991b1b; }
    .pill-neutral { background: #e5e7eb; color: #374151; }

    /* --- Step rail (the business journey) ------------------------------ */
    .gs-rail {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin: 0.2rem 0 1.2rem;
    }
    .gs-rail-step {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        border: 1px solid var(--gs-line);
        border-radius: 999px;
        padding: 0.35rem 0.9rem 0.35rem 0.5rem;
        font-size: 0.84rem;
        font-weight: 600;
        color: var(--gs-muted);
        background: var(--gs-surface);
    }
    .gs-rail-num {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.5rem; height: 1.5rem;
        border-radius: 50%;
        background: #eef2f7;
        color: var(--gs-ink-soft);
        font-size: 0.78rem;
        font-weight: 700;
    }
    .gs-rail-step.active {
        border-color: var(--gs-brand);
        color: var(--gs-brand);
        box-shadow: 0 4px 14px rgba(79, 70, 229, 0.16);
    }
    .gs-rail-step.active .gs-chip,
    .gs-rail-step.active { background: #f5f3ff; }
    .gs-rail-step.done { color: var(--gs-ok); border-color: rgba(22, 101, 52, 0.28); }
    .gs-rail-step.done .gs-num {
        background: var(--gs-ok-bg); color: var(--gs-ok);
    }
    .gs-num {
        display: inline-flex; align-items: center; justify-content: center;
        width: 1.5rem; height: 1.5rem; border-radius: 50%;
        background: #eef2f7; color: var(--gs-ink-soft);
        font-size: 0.78rem; font-weight: 700;
    }

    /* --- Empty state --------------------------------------------------- */
    .gs-empty {
        border: 1px dashed var(--gs-line);
        border-radius: var(--gs-radius);
        background: var(--gs-surface-2);
        padding: 1.4rem 1.5rem;
        text-align: center;
        color: var(--gs-ink-soft);
    }
    .gs-empty .gs-empty-icon { font-size: 1.6rem; display: block; margin-bottom: 0.4rem; }
    .gs-empty strong { color: var(--gs-ink); display: block; margin-bottom: 0.2rem; }

    /* --- Review findings ---------------------------------------------- */
    .gs-finding {
        border-radius: 12px;
        padding: 0.55rem 0.8rem;
        margin: 0.3rem 0;
        border-left: 4px solid var(--gs-line);
        background: var(--gs-surface-2);
        color: var(--gs-ink-soft);
        font-size: 0.92rem;
        line-height: 1.45;
    }
    .gs-finding.error { border-left-color: var(--gs-stop); background: #fef2f2; }
    .gs-finding.warning { border-left-color: #d97706; background: #fffbeb; }
    .gs-finding.info { border-left-color: var(--gs-brand); background: #eef2ff; }

    /* --- Check rows (clarity check) ----------------------------------- */
    .gs-check { display: flex; gap: 0.6rem; padding: 0.35rem 0; border-bottom: 1px solid var(--gs-line); }
    .gs-check:last-child { border-bottom: none; }
    .gs-check .gs-check-icon { flex: 0 0 auto; font-size: 1rem; line-height: 1.5; }
    .gs-check .gs-check-body { flex: 1 1 auto; }
    .gs-check .gs-check-label { font-weight: 600; color: var(--gs-ink); }
    .gs-check .gs-check-detail { color: var(--gs-muted); font-size: 0.9rem; }

    /* --- Buttons ------------------------------------------------------- */
    div.stButton > button, div.stFormSubmitButton > button, div.stDownloadButton > button {
        border-radius: 11px;
        font-weight: 600;
        transition: transform 0.08s ease, box-shadow 0.12s ease, border-color 0.12s ease;
    }
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {
        transform: translateY(-1px);
        border-color: var(--gs-brand);
        color: var(--gs-brand);
    }
    div.stButton > button[kind="primary"],
    div.stFormSubmitButton > button[kind="primary"],
    button[data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, #4f46e5, #7c3aed);
        border: none;
        color: #ffffff;
        box-shadow: 0 8px 20px rgba(79, 70, 229, 0.28);
    }
    div.stButton > button[kind="primary"]:hover,
    button[data-testid="stBaseButton-primary"]:hover {
        color: #ffffff;
        filter: brightness(1.05);
    }

    /* --- Metrics as cards --------------------------------------------- */
    div[data-testid="stMetric"] {
        background: var(--gs-surface);
        border: 1px solid var(--gs-line);
        border-radius: 14px;
        padding: 0.9rem 1rem;
        box-shadow: var(--gs-shadow-sm);
    }
    div[data-testid="stMetricLabel"] { color: var(--gs-muted); }
    div[data-testid="stMetricValue"] { color: var(--gs-ink); }

    /* --- Tabs ---------------------------------------------------------- */
    div[data-testid="stTabs"] button[role="tab"] {
        font-weight: 600;
        padding: 0.55rem 0.4rem;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { color: var(--gs-brand); }
</style>
"""


def inject_styles() -> None:
    """Add Gigsie's shared CSS to the page."""
    st.markdown(_CSS, unsafe_allow_html=True)


def go(view: str) -> None:
    """Switch the active view and rerun."""
    st.session_state["view"] = view
    st.rerun()


def nav_sidebar() -> None:
    """Persistent Home / Business / Student navigation and product identity."""
    with st.sidebar:
        st.markdown("### 🧩 Gigsie")
        st.caption(PRODUCT_NAME)
        st.divider()
        current = st.session_state.get("view", VIEW_HOME)
        for view in (VIEW_HOME, VIEW_BUSINESS, VIEW_STUDENT):
            active = view == current
            if st.button(
                f"{_VIEW_ICON[view]}  {VIEW_TO_LABEL[view]}",
                key=f"nav_{view}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                if not active:
                    go(view)
        st.divider()
        st.caption(
            "Local prototype: data is stored on this device only. No real accounts, "
            "payments, messaging, or video calls."
        )


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def hero(
    badge: str = "Hacktoberfest 2026 · early prototype",
    title: str = "🧩 Gigsie",
    subtitle: str = TAGLINE,
) -> None:
    """Render the product hero banner."""
    badge_html = f'<span class="gigsie-badge">{badge}</span>' if badge else ""
    st.markdown(
        f"""
        <div class="gigsie-hero">
            <h1>{title}</h1>
            <p>{subtitle}</p>
            {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def eyebrow(text: str) -> None:
    """A small uppercase label above a heading."""
    st.markdown(f'<div class="gs-eyebrow">{text}</div>', unsafe_allow_html=True)


def chip(text: str, tone: str = "neutral") -> str:
    """Return an inline HTML chip. ``tone`` is ok/warn/stop/info/neutral."""
    safe_tone = tone if tone in {"ok", "warn", "stop", "info", "neutral"} else "neutral"
    return f'<span class="gs-chip tone-{safe_tone}">{text}</span>'


def finding_html(level: str, message: str) -> str:
    """Return an inline HTML block for a validation finding."""
    safe_level = level if level in {"error", "warning", "info"} else "info"
    return f'<div class="gs-finding {safe_level}">{message}</div>'


def empty_state(icon: str, title: str, body: str) -> None:
    """Render a friendly empty state (no invented data, just guidance)."""
    st.markdown(
        f"""
        <div class="gs-empty">
            <span class="gs-empty-icon">{icon}</span>
            <strong>{title}</strong>
            <span>{body}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def step_rail(steps: list[str], active: int) -> None:
    """Render a horizontal progress rail. ``active`` is a 0-based index.

    Steps before ``active`` are shown as done, the active one is highlighted, and
    later steps stay neutral. This is orientation only - it never gates a flow.
    """
    parts: list[str] = []
    for index, label in enumerate(steps):
        if index < active:
            state, number = "done", "✓"
        elif index == active:
            state, number = "active", str(index + 1)
        else:
            state, number = "", str(index + 1)
        parts.append(
            f'<span class="gs-rail-step {state}"><span class="gs-num">{number}</span>{label}</span>'
        )
    st.markdown('<div class="gs-rail">' + "".join(parts) + "</div>", unsafe_allow_html=True)


def info_card(title: str, body: str, accent: str = "brand") -> None:
    """Render a static informational card."""
    cls = "gs-card--accent" if accent == "accent" else "gs-card--brand"
    st.markdown(
        f'<div class="gs-card {cls}"><h4>{title}</h4><p>{body}</p></div>',
        unsafe_allow_html=True,
    )


def bullet_list(items: Any, empty_text: str = "None.") -> None:
    """Render a list of items as markdown bullets, or a caption when empty."""
    values = [str(item) for item in items] if isinstance(items, (list, tuple)) else []
    if not values:
        st.caption(empty_text)
        return
    for item in values:
        st.markdown(f"- {item}")


def show_findings(findings: Any, ok_text: str | None = "No issues found.") -> None:
    """Render validation findings with a clear severity."""
    if not isinstance(findings, (list, tuple)) or not findings:
        if ok_text:
            st.caption(ok_text)
        return
    for finding in findings:
        level = finding.get("level") if isinstance(finding, dict) else None
        message = finding.get("message", "") if isinstance(finding, dict) else str(finding)
        if level == "error":
            st.error(message)
        elif level == "warning":
            st.warning(message)
        else:
            st.info(message)


def status_pill(status: Any, label: Any = None) -> str:
    """Render a status as a colored pill."""
    text = str(label or status or "unknown")
    key = str(status or "neutral").strip().lower().replace(" ", "_")
    return f'<span class="gigsie-pill pill-{key}">{text}</span>'


def sample_tag() -> str:
    """Return the inline 'SAMPLE' tag used for illustrative data."""
    return '<span class="gigsie-sample-tag">SAMPLE</span>'


def passport_value(section: Any) -> None:
    """Render one Gig Passport section, marking unknown information honestly."""
    if not isinstance(section, dict):
        return
    value = section.get("value")
    kind = section.get("kind", "text")
    needs = section.get("needs_clarification")

    if kind == "list":
        items = [str(item) for item in value] if isinstance(value, (list, tuple)) else []
        if items:
            bullet_list(items)
        elif needs:
            st.caption("Needs clarification - not specified yet.")
        else:
            st.caption("None specified.")
    elif kind == "budget":
        try:
            amount = float(value)
        except (TypeError, ValueError):
            amount = 0.0
        if amount:
            st.markdown(f"**{amount:,.0f} INR**")
        elif needs:
            st.caption("Needs clarification - not specified yet.")
        else:
            st.caption("None specified.")
    else:
        text = str(value or "").strip()
        if text:
            st.write(text)
        elif needs:
            st.caption("Needs clarification - not specified yet.")
        else:
            st.caption("None specified.")


def back_button(label: str = "← Back to start", key: str = "back_to_landing") -> None:
    """Render a back-to-home button."""
    if st.button(label, key=key):
        go(VIEW_HOME)


def section_heading(title: str, caption: str | None = None) -> None:
    """Render a consistent section heading with optional caption."""
    st.markdown(f"### {title}")
    if caption:
        st.caption(caption)
