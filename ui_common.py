"""Shared Streamlit presentation layer for Gigsie.

This module owns the whole visual system and the navigation shell so ``app.py``,
``student_ui.py`` and ``business_ui.py`` all look like one product.

It is presentation only: it renders HTML, styles, and navigation. Every rule and
every write lives in the backend modules, and every count it shows is read from
local storage. Nothing here invents users, metrics, matches, or activity.

Design (matched to the reference designs)
-----------------------------------------
* A pale lavender canvas with one inset white "shell" holding a lavender sidebar
  and a white content canvas, rounded like the references.
* A permanent left sidebar: wordmark, grouped navigation with a clearly
  highlighted active item, and an honest prototype footer.
* A compact top header: breadcrumb, a search field that really filters saved
  gigs, a Business/Student role switch, the real local profile, and one primary
  action.
* White cards with thin borders, restrained shadows, metric tiles, marketplace
  job cards, module cards, status pills, and purposeful empty states.

Everything is scoped CSS over Streamlit's own widgets - no new frontend
framework, no new dependencies, no static HTML mockups of the product.
"""

from __future__ import annotations

from html import escape as _escape
from typing import Any

import streamlit as st

import validation


# ---------------------------------------------------------------------------
# Product identity
# ---------------------------------------------------------------------------
TAGLINE = "Turn vague business requests into clear, achievable freelance gigs."
PRODUCT_NAME = "Gigsie"
PRODUCT_DESCRIPTOR = "AI task briefs, fair scopes, and gig passports"

VIEW_HOME = "landing"
VIEW_BUSINESS = "business"
VIEW_STUDENT = "student"

VIEW_LABEL = {VIEW_HOME: "Overview", VIEW_BUSINESS: "Business", VIEW_STUDENT: "Student"}
VIEW_ICON = {VIEW_HOME: "◈", VIEW_BUSINESS: "✦", VIEW_STUDENT: "◎"}

# Sections inside a view.
SEC_OVERVIEW = ""              # the app home
SEC_CREATE = "create"          # the request form, then the FairScope review
SEC_PASSPORT = "passport"      # the Gig Passport editor and publishing
SEC_PUBLISHED = "published"    # published + sample gigs
SEC_APPLICANTS = "applicants"  # applicants and interviews
SEC_STUDENT_HOME = "home"      # student overview
SEC_FIND_WORK = "find_work"    # browse gigs + detail + proposal
SEC_PROFILE = "profile"        # student profile
SEC_APPLICATIONS = "applications"
SEC_ASSESSMENTS = "assessments"
SEC_INTERVIEWS = "interviews"

SECTION_LABEL = {
    SEC_OVERVIEW: "Overview",
    SEC_CREATE: "Create with AI",
    SEC_PASSPORT: "Gig Passport",
    SEC_PUBLISHED: "Published Gigs",
    SEC_APPLICANTS: "Applicants & Interviews",
    SEC_STUDENT_HOME: "Student Overview",
    SEC_FIND_WORK: "Find Work",
    SEC_PROFILE: "My Profile",
    SEC_APPLICATIONS: "My Applications",
    SEC_ASSESSMENTS: "Skill Assessments",
    SEC_INTERVIEWS: "Interviews",
}

# One navigation system: the sidebar is the only place pages are listed, and it
# is always visible. Gig Passport and Student Overview stay real routes but are
# reached through the workflow, so they are not duplicated as top-level items.
NAV_GROUPS: list[tuple[str, list[tuple[str, str, str, str]]]] = [
    (
        "Workspace",
        [
            (VIEW_HOME, SEC_OVERVIEW, "◈", "Overview"),
        ],
    ),
    (
        "Business",
        [
            (VIEW_BUSINESS, SEC_CREATE, "✦", "Create with AI"),
            (VIEW_BUSINESS, SEC_PUBLISHED, "▤", "Published Gigs"),
            (VIEW_BUSINESS, SEC_APPLICANTS, "◫", "Applicants & Interviews"),
        ],
    ),
    (
        "Student",
        [
            (VIEW_STUDENT, SEC_FIND_WORK, "◍", "Find Work"),
            (VIEW_STUDENT, SEC_PROFILE, "◑", "My Profile"),
            (VIEW_STUDENT, SEC_APPLICATIONS, "✉", "My Applications"),
            (VIEW_STUDENT, SEC_ASSESSMENTS, "✔", "Skill Assessments"),
            (VIEW_STUDENT, SEC_INTERVIEWS, "◷", "Interviews"),
        ],
    ),
]

ROLE_BUSINESS = "Business"
ROLE_STUDENT = "Student"


# ---------------------------------------------------------------------------
# Stylesheets
# ---------------------------------------------------------------------------
_FONT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
+&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap');
</style>
"""

_CSS = """
<style>
    :root {
        /* Surfaces */
        --gs-canvas: #f3f1fb;
        --gs-sidebar: #efeafa;
        --gs-shell: #ffffff;
        --gs-surface: #ffffff;
        --gs-surface-2: #faf9fe;
        --gs-surface-3: #f4f1fd;
        /* Text */
        --gs-ink: #28283a;
        --gs-ink-2: #3d3d55;
        --gs-muted: #77778a;
        --gs-faint: #9c9cb0;
        /* Lines */
        --gs-line: #e8e5f0;
        --gs-line-2: #dcd7ec;
        /* Accent */
        --gs-brand: #7353e8;
        --gs-brand-2: #a58af4;
        --gs-brand-ink: #5736cf;
        --gs-brand-soft: #f1ecfe;
        /* Status */
        --gs-ok: #128a52;
        --gs-ok-bg: #e2f6ec;
        --gs-warn: #92590c;
        --gs-warn-bg: #fdf0d8;
        --gs-stop: #a32c2c;
        --gs-stop-bg: #fde9e9;
        --gs-info: #35359f;
        --gs-info-bg: #e9e8fc;
        /* Shape */
        --gs-radius: 18px;
        --gs-radius-sm: 12px;
        --gs-radius-xs: 9px;
        --gs-shadow: 0 16px 34px rgba(46, 36, 92, 0.07);
        --gs-shadow-sm: 0 3px 12px rgba(46, 36, 92, 0.06);
        --gs-shadow-accent: 0 10px 24px rgba(115, 83, 232, 0.26);
    }

    /* --- Typography ----------------------------------------------------- */
    html, body, [class*="st-"]:not([data-testid="stIconMaterial"]),
    button, input, textarea, select {
        font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        color: var(--gs-ink);
    }
    h1, h2, h3, h4, .gs-display, .gs-display span, .gs-wordmark {
        font-family: "Plus Jakarta Sans", "Inter", "Segoe UI", Arial, sans-serif;
        letter-spacing: -0.022em;
    }
    h2 { font-weight: 800; }
    h3 { font-weight: 700; }
    h4 { font-weight: 700; }
    p, li { line-height: 1.55; }
    a { color: var(--gs-brand); text-decoration: none; }

    /* Streamlit styles its own headings with a single-class emotion selector
       (Source Sans, 2.75rem for h1). That ties with a bare class selector on
       specificity and then wins on source order, so headings rendered from
       markdown ignored this stylesheet entirely. These rules are scoped to the
       content area, which outranks the emotion class, and sit before the
       component rules below so `.gs-job h4` and friends still win for cards. */
    [data-testid="stMainBlockContainer"] h1:not([class]),
    [data-testid="stMainBlockContainer"] h2:not([class]),
    [data-testid="stMainBlockContainer"] h3:not([class]),
    [data-testid="stMainBlockContainer"] h4:not([class]),
    [data-testid="stMainBlockContainer"] h5:not([class]) {
        font-family: "Plus Jakarta Sans", "Inter", "Segoe UI", Arial, sans-serif;
        letter-spacing: -0.02em;
        color: var(--gs-ink);
    }
    [data-testid="stMainBlockContainer"] h1:not([class]) { font-size: 1.35rem; font-weight: 800; }
    [data-testid="stMainBlockContainer"] h2:not([class]) { font-size: 1.12rem; font-weight: 750; }
    [data-testid="stMainBlockContainer"] h3:not([class]) { font-size: 1rem; font-weight: 700; }
    [data-testid="stMainBlockContainer"] h4:not([class]) { font-size: 0.95rem; font-weight: 700; }
    [data-testid="stMainBlockContainer"] h5:not([class]) { font-size: 0.9rem; font-weight: 700; }

    /* --- Canvas and the inset app shell --------------------------------- */
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(1100px 520px at 8% -10%, #efe9fd 0%, rgba(239,233,253,0) 60%),
            linear-gradient(160deg, #f6f4fd 0%, #f1edfb 45%, #ece7f9 100%);
    }
    [data-testid="stHeader"] {
        background: transparent;
        box-shadow: none;
    }
    /* The references have no top chrome: hide Streamlit's Deploy / overflow menu. */
    [data-testid="stToolbar"] { visibility: hidden; height: 0; }
    [data-testid="stMain"] { background: transparent; }

    /* Sidebar becomes the lavender card of the shell. */
    section[data-testid="stSidebar"] {
        background: transparent;
        width: 268px !important;
        min-width: 268px !important;
        border-right: none;
        position: relative;
    }
    section[data-testid="stSidebar"] > div { padding: 0; }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        background: var(--gs-sidebar);
        border: 1px solid var(--gs-line);
        border-right: none;
        border-radius: var(--gs-radius) 0 0 var(--gs-radius);
        margin: 14px 0 14px 14px;
        padding: 1.1rem 0.8rem 1rem 0.95rem;
        box-shadow: none;
        height: calc(100% - 28px);
        overflow-y: auto;
    }
    /* Streamlit's own sidebar header only holds the logo spacer and the collapse
       button. Lift the button out of the flow so the card starts at the top. */
    /* Streamlit's own sidebar header only holds the logo spacer and the collapse
       button. Both are removed: the wordmark below is the header, and a collapse
       control would let the primary navigation disappear. */
    section[data-testid="stSidebar"] div[data-testid="stSidebarHeader"] {
        display: none;
    }
    section[data-testid="stSidebar"] div[data-testid="stSidebarLogoSpacer"] {
        display: none;
    }

    /* The content area is the white card of the shell. The width is capped so a
       wide window does not stretch body text into unreadable line lengths. */
    [data-testid="stMainBlockContainer"], .block-container {
        background: var(--gs-shell);
        border: 1px solid var(--gs-line);
        border-left: none;
        border-radius: 0 var(--gs-radius) var(--gs-radius) 0;
        box-shadow: var(--gs-shadow);
        margin: 14px 14px 14px 0;
        padding: 1.1rem 1.5rem 2.5rem;
        max-width: 1320px;
        min-height: calc(100vh - 28px);
    }
    /* Body copy is capped well below the card width for comfortable reading. */
    [data-testid="stMainBlockContainer"] p,
    [data-testid="stMainBlockContainer"] li { max-width: 88ch; }

    /* --- Sidebar navigation --------------------------------------------- */
    .gs-wordmark {
        display: flex; align-items: center; gap: 0.55rem;
        font-size: 1.2rem; font-weight: 800; color: var(--gs-ink);
    }
    .gs-wordmark em {
        font-style: normal; color: var(--gs-brand);
    }
    .gs-brand-mark {
        width: 2rem; height: 2rem; border-radius: 11px;
        display: inline-flex; align-items: center; justify-content: center;
        background: linear-gradient(135deg, var(--gs-brand), var(--gs-brand-2));
        color: #fff; font-size: 0.95rem; font-weight: 700;
        box-shadow: var(--gs-shadow-accent);
    }
    .gs-brand-sub {
        font-size: 0.76rem; color: var(--gs-muted); line-height: 1.35;
        margin: 0.45rem 0 0.15rem;
    }
    .gs-nav-label {
        text-transform: uppercase; letter-spacing: 0.1em;
        font-size: 0.68rem; font-weight: 700; color: var(--gs-faint);
        margin: 1.15rem 0 0.4rem 0.6rem;
    }
    .gs-nav-label:first-of-type { margin-top: 0.2rem; }

    /* The sidebar is the primary navigation, so it opens expanded and its
       toggle is styled to match the shell rather than removed.

       It is deliberately NOT hidden: Streamlit remembers the collapsed state in
       the browser, so hiding both the collapse button and the expand control can
       strand a returning user with no way back to the navigation at all. */
    section[data-testid="stSidebar"] div[data-testid="stSidebarCollapseButton"] button,
    div[data-testid="stExpandSidebarButton"] button,
    button[data-testid="stExpandSidebarButton"] {
        background: rgba(255, 255, 255, 0.75);
        border: 1px solid var(--gs-line-2);
        border-radius: 9px;
        color: var(--gs-ink-2);
        width: 30px;
        height: 30px;
    }
    section[data-testid="stSidebar"] div[data-testid="stSidebarCollapseButton"] button:hover,
    div[data-testid="stExpandSidebarButton"] button:hover,
    button[data-testid="stExpandSidebarButton"]:hover {
        background: #fff;
        color: var(--gs-brand-ink);
        border-color: var(--gs-brand-2);
    }
    /* Streamlit's own header only holds the logo spacer; drop the empty space
       but keep the toggle in the flow so it stays clickable. */
    section[data-testid="stSidebar"] div[data-testid="stSidebarLogoSpacer"] {
        display: none;
    }
    section[data-testid="stSidebar"] {
        /* Forced, because this sidebar *is* the navigation: on a narrow window
           Streamlit slides it away, and that must never be able to strand the
           user with no way to reach another page. The toggle is still visible
           above, so the layout never fights the user. */
        min-width: 248px !important;
        width: 248px !important;
        max-width: 248px !important;
        transform: none !important;
    }
    /* The expand affordance Streamlit shows in the top header when it thinks the
       sidebar is collapsed: keep it on-brand and clickable. */
    section[data-testid="stSidebar"] div[data-testid="stSidebarCollapseButton"],
    [data-testid="stExpandSidebarButton"] { display: flex !important; }
    /* The nav stays at the top and the honest footer sits at the bottom, so the
       space between them reads as deliberate rather than as a blank panel. */
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div {
        display: flex; flex-direction: column; min-height: 100%;
    }
    section[data-testid="stSidebar"] .gs-sidebar-foot { margin-top: auto; }

    section[data-testid="stSidebar"] div.stButton > button {
        width: 100%;
        justify-content: flex-start;
        text-align: left;
        background: transparent;
        border: 1px solid transparent;
        color: var(--gs-ink-2);
        font-size: 0.95rem;
        font-weight: 600;
        border-radius: var(--gs-radius-sm);
        padding: 0.6rem 0.8rem;
        box-shadow: none;
        white-space: nowrap;
    }
    section[data-testid="stSidebar"] div.stButton > button:hover {
        background: rgba(115, 83, 232, 0.10);
        border-color: transparent;
        color: var(--gs-brand-ink);
    }
    section[data-testid="stSidebar"] div.stButton > button[kind="primary"],
    section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {
        background: var(--gs-shell);
        color: var(--gs-brand-ink);
        border: 1px solid var(--gs-line-2);
        box-shadow: 0 6px 16px rgba(70, 50, 150, 0.10);
    }
    section[data-testid="stSidebar"] div.stButton > button[kind="primary"]:hover,
    section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:hover {
        background: var(--gs-shell);
        color: var(--gs-brand-ink);
        border-color: var(--gs-brand-2);
    }
    .gs-sidebar-foot {
        margin-top: 1.4rem; padding: 1rem 0.8rem 0.2rem;
        border-top: 1px solid var(--gs-line-2);
        font-size: 0.72rem; color: var(--gs-faint); line-height: 1.45;
    }

    /* --- Top header ------------------------------------------------------ */
    .gs-top-rule {
        height: 1px; background: var(--gs-line);
        margin: 0.85rem 0 1.25rem;
    }
    .gs-crumb {
        font-size: 0.85rem; color: var(--gs-faint); font-weight: 600;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .gs-crumb b { color: var(--gs-ink-2); font-weight: 700; }
    .gs-crumb span { margin: 0 0.35rem; }
    .gs-no-profile {
        font-size: 0.74rem; color: var(--gs-faint); font-weight: 600;
        border: 1px dashed var(--gs-line-2); border-radius: 999px;
        padding: 0.32rem 0.65rem; display: inline-block; white-space: nowrap;
    }

    .gs-profile {
        display: inline-flex; align-items: center; gap: 0.5rem;
        border: 1px solid var(--gs-line);
        border-radius: 999px; background: var(--gs-surface-2);
        padding: 0.3rem 0.7rem 0.3rem 0.32rem;
        max-width: 100%; overflow: hidden;
    }
    .gs-profile > span:last-child { min-width: 0; overflow: hidden; }
    .gs-avatar {
        width: 1.7rem; height: 1.7rem; border-radius: 50%; flex-shrink: 0;
        display: inline-flex; align-items: center; justify-content: center;
        background: linear-gradient(135deg, var(--gs-brand), var(--gs-brand-2));
        color: #fff; font-size: 0.75rem; font-weight: 700;
    }
    .gs-profile-name {
        font-size: 0.82rem; font-weight: 700; line-height: 1.15;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .gs-profile-sub {
        font-size: 0.66rem; color: var(--gs-muted); line-height: 1.15;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }

    /* --- Page headings --------------------------------------------------- */
    .gs-eyebrow {
        text-transform: uppercase; letter-spacing: 0.1em;
        font-size: 0.7rem; font-weight: 700; color: var(--gs-brand);
    }
    .gs-display {
        margin: 0 0 0.1rem; font-weight: 800;
        font-size: 1.7rem; line-height: 1.15;
    }
    .gs-display .off { color: #c9c5da; }
    .gs-display .mid { color: #8d88a8; }
    .gs-page-head { margin: 0 0 0.85rem; }
    /* Scoped so it outranks Streamlit's own h1 styling, which is injected
       after this stylesheet and would otherwise render the title at 2.75rem. */
    [data-testid="stMainBlockContainer"] .gs-page-title {
        margin: 0.1rem 0 0; font-size: 1.35rem; font-weight: 800;
        letter-spacing: -0.02em;
        font-family: "Plus Jakarta Sans", "Inter", "Segoe UI", Arial, sans-serif;
        color: var(--gs-ink);
    }
    [data-testid="stMainBlockContainer"] .gs-display {
        font-family: "Plus Jakarta Sans", "Inter", "Segoe UI", Arial, sans-serif;
        /* Scoped so Streamlit's own h1 sizing (2.75rem, injected later) loses. */
        font-size: 1.7rem;
        line-height: 1.15;
        font-weight: 800;
        margin: 0 0 0.1rem;
    }
    [data-testid="stMainBlockContainer"] .gs-section-title {
        font-family: "Plus Jakarta Sans", "Inter", "Segoe UI", Arial, sans-serif;
    }
    [data-testid="stMainBlockContainer"] .gs-panel-title {
        font-family: "Plus Jakarta Sans", "Inter", "Segoe UI", Arial, sans-serif;
    }
    .gs-page-sub {
        margin: 0.3rem 0 0; color: var(--gs-muted);
        font-size: 0.9rem; max-width: 68ch;
    }
    .gs-section-title {
        font-size: 1rem; font-weight: 750; margin: 0.1rem 0 0.1rem;
        font-family: "Plus Jakarta Sans", "Inter", sans-serif;
        letter-spacing: -0.018em;
    }
    .gs-section-caption {
        color: var(--gs-muted); font-size: 0.86rem; margin-bottom: 0.6rem;
    }

    /* --- Metric tiles (reference: small label, big number, muted hint) --- */
    .gs-stat {
        background: var(--gs-surface);
        border: 1px solid var(--gs-line);
        border-radius: var(--gs-radius);
        padding: 0.9rem 1rem;
        box-shadow: var(--gs-shadow-sm);
        height: 100%;
        min-height: 6.4rem;
        display: flex; flex-direction: column;
    }
    .gs-stat-label {
        font-size: 0.86rem; font-weight: 600; color: var(--gs-muted);
        line-height: 1.3;
    }
    .gs-stat-value {
        font-size: 1.75rem; font-weight: 800; line-height: 1.05;
        letter-spacing: -0.03em; color: var(--gs-ink);
        font-family: "Plus Jakarta Sans", "Inter", sans-serif;
        margin-top: auto;
    }
    .gs-stat-value.brand { color: var(--gs-brand); }
    .gs-stat-hint {
        color: var(--gs-faint); font-size: 0.76rem; margin-top: 0.28rem;
    }
    .gs-stat.tone-ok .gs-stat-value { color: var(--gs-ok); }
    .gs-stat.tone-warn .gs-stat-value { color: var(--gs-warn); }
    .gs-stat.tone-info .gs-stat-value { color: var(--gs-info); }

    /* --- Equal-height cards in a grid row -------------------------------
       Streamlit stretches the columns but leaves each column as a block, so a
       column never fills. Making the column a flex column lets the card marked
       .gs-panel--fill take the height of the tallest card in its row. */
    [data-testid="stHorizontalBlock"] { align-items: stretch; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        display: flex;
        flex-direction: column;
        /* Streamlit's columns default to min-width:auto, so one long title
           stretches the whole row instead of wrapping inside its column. */
        min-width: 0;
    }
    /* Responsive fallback: below this width a multi-column grid is too cramped to
       read, so each column takes a full row instead of squeezing. */
    @media (max-width: 1024px) {
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            flex: 1 1 100% !important;
            width: 100%;
        }
    }
    /* A metric tile is always one of a row of identical tiles, so it stretches
       to the tallest one without the caller having to ask for it. */
    [data-testid="stElementContainer"]:has(.gs-stat) { flex: 1 1 auto; }
    [data-testid="stElementContainer"]:has(.gs-stat) .stMarkdown,
    [data-testid="stElementContainer"]:has(.gs-stat) .stMarkdown > div,
    [data-testid="stElementContainer"]:has(.gs-stat) [data-testid="stMarkdownContainer"] {
        height: 100%;
    }
    .gs-stat { height: 100%; }

    [data-testid="stElementContainer"]:has(.gs-panel--fill) { flex: 1 1 auto; }
    [data-testid="stElementContainer"]:has(.gs-job--fill) { flex: 1 1 auto; }
    /* Streamlit wraps markdown in three nested boxes; a percentage height only
       resolves once each of them is stretched to its parent. */
    [data-testid="stElementContainer"]:has(.gs-panel--fill) .stMarkdown,
    [data-testid="stElementContainer"]:has(.gs-panel--fill) .stMarkdown > div,
    [data-testid="stElementContainer"]:has(.gs-panel--fill) [data-testid="stMarkdownContainer"],
    [data-testid="stElementContainer"]:has(.gs-job--fill) .stMarkdown,
    [data-testid="stElementContainer"]:has(.gs-job--fill) .stMarkdown > div,
    [data-testid="stElementContainer"]:has(.gs-job--fill) [data-testid="stMarkdownContainer"] {
        height: 100%;
    }
    .gs-panel--fill, .gs-job--fill { height: 100%; }

    /* --- Panels (reference: header + kebab, body, footer tags) ---------- */
    .gs-panel {
        background: var(--gs-surface);
        border: 1px solid var(--gs-line);
        border-radius: var(--gs-radius);
        padding: 0.95rem 1.05rem;
        box-shadow: var(--gs-shadow-sm);
        margin-bottom: 0.75rem;
        display: flex;
        flex-direction: column;
    }
    .gs-panel-head {
        display: flex; align-items: flex-start; justify-content: space-between;
        gap: 0.6rem; margin-bottom: 0.5rem;
    }
    .gs-panel-title {
        margin: 0; font-size: 0.99rem; font-weight: 750;
        font-family: "Plus Jakarta Sans", "Inter", sans-serif;
        letter-spacing: -0.015em;
    }
    .gs-panel-caption {
        margin: 0.15rem 0 0; color: var(--gs-muted); font-size: 0.82rem;
        line-height: 1.4;
    }
    .gs-kebab { color: var(--gs-faint); font-size: 1.1rem; line-height: 1; letter-spacing: 1px; }
    .gs-panel-body {
        color: var(--gs-ink-2); font-size: 0.9rem;
        display: flex; flex-direction: column; flex: 1 1 auto;
    }
    .gs-panel-body p { margin: 0.25rem 0; }
    .gs-panel-foot {
        margin-top: auto; padding-top: 0.7rem;
        border-top: 1px solid var(--gs-line);
        min-width: 0;
    }
    .gs-panel-foot + .gs-panel-foot { border-top: none; padding-top: 0.35rem; }
    .gs-panel.accent { border-top: 3px solid var(--gs-brand); }
    .gs-panel.alt { border-top: 3px solid var(--gs-brand-2); }

    /* --- Marketplace job card (reference project card) ------------------- */
    .gs-job {
        background: var(--gs-surface);
        border: 1px solid var(--gs-line);
        border-radius: var(--gs-radius);
        box-shadow: var(--gs-shadow-sm);
        padding: 0.9rem 1rem 0.85rem;
        margin-bottom: 0.5rem;
        display: flex; flex-direction: column;
    }
    .gs-job-top {
        display: flex; align-items: center; gap: 0.5rem;
        font-size: 0.75rem; color: var(--gs-faint); margin-bottom: 0.4rem;
    }
    .gs-job-top .kebab { margin-left: auto; }
    .gs-job h4 { margin: 0 0 0.25rem; font-size: 0.98rem; line-height: 1.35; }
    .gs-job .gs-job-ctx {
        color: var(--gs-muted); font-size: 0.8rem; margin: 0 0 0.35rem;
    }
    /* Two lines only: keeps every card in a row the same height without
       truncating the gig itself (the detail page shows everything). */
    .gs-job .gs-job-text {
        color: var(--gs-ink-2); font-size: 0.87rem; margin: 0 0 0.45rem;
        line-height: 1.45;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
        overflow: hidden;
    }
    .gs-job .gs-job-match {
        color: var(--gs-brand-ink); font-size: 0.79rem; font-weight: 600;
        margin: 0 0 0.4rem;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .gs-job-tags { max-height: 3.3rem; overflow: hidden; }
    .gs-job-foot {
        margin-top: auto; padding-top: 0.6rem;
        display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap;
    }
    .gs-money { font-weight: 750; color: var(--gs-ink); font-size: 0.92rem; }
    .gs-job-meta { color: var(--gs-muted); font-size: 0.79rem; }

    /* --- Table (reference data table) ------------------------------------ */
    .gs-table-wrap {
        border: 1px solid var(--gs-line);
        border-radius: var(--gs-radius);
        overflow-x: auto;
    }
    .gs-table { width: 100%; border-collapse: collapse; font-size: 0.89rem; }
    .gs-table th {
        text-align: left; font-weight: 650; color: var(--gs-ink-2);
        padding: 0.7rem 0.9rem; border-bottom: 1px solid var(--gs-line);
        background: var(--gs-surface-2);
    }
    .gs-table th:first-child { border-top-left-radius: var(--gs-radius-sm); }
    .gs-table th:last-child { border-top-right-radius: var(--gs-radius-sm); }
    .gs-table td {
        padding: 0.7rem 0.9rem; border-bottom: 1px solid var(--gs-line);
        color: var(--gs-ink-2); vertical-align: middle;
    }
    .gs-table tr:last-child td { border-bottom: none; }
    .gs-table td b { color: var(--gs-ink); }
    .gs-table td.muted { color: var(--gs-muted); }

    /* --- Chips, tags, pills ---------------------------------------------- */
    .gs-chip {
        display: inline-block; border-radius: 999px;
        padding: 0.2rem 0.68rem; font-size: 0.77rem; font-weight: 600;
        margin: 0.12rem 0.3rem 0.12rem 0; border: 1px solid transparent;
        /* Wrap only when a chip is genuinely wider than its card. */
        max-width: 100%; white-space: normal; overflow-wrap: break-word;
    }
    .gs-chip.tone-ok { background: var(--gs-ok-bg); color: var(--gs-ok); }
    .gs-chip.tone-warn { background: var(--gs-warn-bg); color: var(--gs-warn); }
    .gs-chip.tone-stop { background: var(--gs-stop-bg); color: var(--gs-stop); }
    .gs-chip.tone-info { background: var(--gs-brand-soft); color: var(--gs-brand-ink); }
    .gs-chip.tone-neutral { background: #eef0f6; color: var(--gs-ink-2); }
    .gs-tag {
        display: inline-block; background: var(--gs-surface-2);
        border: 1px solid var(--gs-line); color: var(--gs-ink-2);
        border-radius: 7px; padding: 0.14rem 0.5rem;
        font-size: 0.76rem; font-weight: 600; margin: 0.1rem 0.25rem 0.1rem 0;
        /* Wrap only when a tag is genuinely wider than its card. */
        max-width: 100%; white-space: normal; overflow-wrap: break-word;
    }

    .gigsie-sample-tag {
        display: inline-block; background: var(--gs-warn-bg); color: var(--gs-warn);
        border-radius: 6px; padding: 0.06rem 0.45rem;
        font-size: 0.66rem; font-weight: 700; letter-spacing: 0.06em;
        vertical-align: middle;
    }

    .gigsie-pill {
        display: inline-block; border-radius: 999px; padding: 0.18rem 0.7rem;
        font-size: 0.75rem; font-weight: 700; white-space: nowrap;
    }
    .pill-submitted { background: var(--gs-brand-soft); color: var(--gs-brand-ink); }
    .pill-shortlisted { background: #e6ecfd; color: #1b3d9e; }
    .pill-interview_requested { background: var(--gs-warn-bg); color: var(--gs-warn); }
    .pill-interview_confirmed { background: var(--gs-ok-bg); color: var(--gs-ok); }
    .pill-requested { background: var(--gs-warn-bg); color: var(--gs-warn); }
    .pill-alternative_proposed { background: #fdeade; color: #9a4a12; }
    .pill-confirmed { background: var(--gs-ok-bg); color: var(--gs-ok); }
    .pill-accepted { background: var(--gs-ok-bg); color: var(--gs-ok); }
    .pill-declined { background: var(--gs-stop-bg); color: var(--gs-stop); }
    .gs-pill-declined { background: var(--gs-stop-bg); color: var(--gs-stop); }
    .pill-rejected { background: var(--gs-stop-bg); color: var(--gs-stop); }
    .pill-open { background: var(--gs-info-bg); color: var(--gs-info); }
    .pill-neutral { background: #eef0f6; color: var(--gs-ink-2); }

    /* --- Step rail ------------------------------------------------------- */
    /* One compact line, not a row of large pills. */
    .gs-rail {
        display: flex; flex-wrap: wrap; align-items: center;
        gap: 0.3rem; margin: 0 0 0.8rem;
    }
    .gs-rail-step {
        display: inline-flex; align-items: center; gap: 0.35rem;
        border: 1px solid var(--gs-line); border-radius: 999px;
        padding: 0.16rem 0.6rem 0.16rem 0.2rem;
        font-size: 0.76rem; font-weight: 600; color: var(--gs-muted);
        background: var(--gs-surface); line-height: 1.3;
    }
    .gs-rail-num, .gs-num {
        display: inline-flex; align-items: center; justify-content: center;
        width: 1.15rem; height: 1.15rem; border-radius: 50%; flex-shrink: 0;
        background: #eef0f6; color: var(--gs-ink-2);
        font-size: 0.68rem; font-weight: 700;
    }
    .gs-rail-step.active {
        border-color: var(--gs-brand-2); color: var(--gs-brand-ink);
        background: var(--gs-brand-soft);
    }
    .gs-rail-step.active .gs-num { background: var(--gs-brand); color: #fff; }
    .gs-rail-step.done { color: var(--gs-ok); border-color: #c2e7d3; }
    .gs-rail-step.done .gs-num { background: var(--gs-ok-bg); color: var(--gs-ok); }

    /* --- Hero and action cards ------------------------------------------- */
    .gigsie-hero {
        position: relative; overflow: hidden;
        background: linear-gradient(120deg, #4c31c4 0%, #7353e8 52%, #9a7bf5 100%);
        color: #ffffff; padding: 1.6rem 1.8rem; border-radius: var(--gs-radius);
        margin-bottom: 1rem; box-shadow: var(--gs-shadow-accent);
    }
    .gigsie-hero::after {
        content: ""; position: absolute; top: -90px; right: -60px;
        width: 260px; height: 260px; border-radius: 50%;
        background: radial-gradient(circle, rgba(255,255,255,0.25), rgba(255,255,255,0));
    }
    .gigsie-hero h1 { margin: 0; font-size: 1.55rem; font-weight: 800; letter-spacing: -0.02em; }
    .gigsie-hero p { margin: 0.45rem 0 0; opacity: 0.95; font-size: 0.97rem; max-width: 60ch; }
    .gigsie-badge {
        display: inline-block; background: rgba(255, 255, 255, 0.17);
        border: 1px solid rgba(255, 255, 255, 0.3); border-radius: 999px;
        padding: 0.22rem 0.75rem; font-size: 0.72rem; font-weight: 600;
        letter-spacing: 0.03em; margin-top: 0.8rem;
    }

    .gs-card {
        background: var(--gs-surface);
        border: 1px solid var(--gs-line);
        border-radius: var(--gs-radius);
        padding: 1.05rem 1.15rem;
        box-shadow: var(--gs-shadow-sm);
        margin-bottom: 0.85rem;
    }
    .gs-card h3 { margin: 0 0 0.3rem; font-size: 1.05rem; }
    .gs-card h4 { margin: 0 0 0.3rem; font-size: 0.98rem; }
    .gs-card p { margin: 0.3rem 0 0; color: var(--gs-muted); }
    .gs-card p strong { color: var(--gs-ink); }
    .gs-card--brand { border-top: 3px solid var(--gs-brand); }
    .gs-card--accent { border-top: 3px solid var(--gs-brand-2); }
    .gs-card--quiet { background: var(--gs-surface-2); box-shadow: none; }
    .gs-note { color: var(--gs-muted); font-size: 0.85rem; }

    /* --- Lists inside panels --------------------------------------------- */
    .gs-list { list-style: none; margin: 0.35rem 0 0; padding: 0; }
    .gs-list li {
        display: flex; align-items: center; gap: 0.6rem;
        padding: 0.55rem 0; border-bottom: 1px solid var(--gs-line);
        font-size: 0.88rem; color: var(--gs-ink-2);
    }
    .gs-list li:last-child { border-bottom: none; }
    .gs-list .grow { flex: 1; min-width: 0; }
    /* Without this a long title forces the whole row, and the card, wider than
       its column instead of wrapping. */
    .gs-list li > * { min-width: 0; overflow-wrap: anywhere; }
    /* Keep a trailing badge or pill at its natural width, but let a row that
       holds only text still shrink and wrap. */
    .gs-list li > *:not(:only-child):last-child { flex-shrink: 0; }
    .gs-list .muted { color: var(--gs-muted); font-size: 0.8rem; }
    .gs-bullet {
        list-style: none; margin: 0.3rem 0 0; padding: 0;
    }
    .gs-bullet li {
        position: relative; padding-left: 1.05rem; margin: 0.24rem 0;
        font-size: 0.89rem; color: var(--gs-ink-2);
    }
    .gs-bullet li::before {
        content: ""; position: absolute; left: 0.15rem; top: 0.62em;
        width: 5px; height: 5px; border-radius: 50%; background: var(--gs-brand-2);
    }
    .gs-kv { display: flex; justify-content: space-between; gap: 1rem; font-size: 0.86rem; padding: 0.28rem 0; }
    .gs-kv span { color: var(--gs-muted); }
    .gs-kv b { color: var(--gs-ink); font-weight: 650; text-align: right; }

    /* --- Empty state ----------------------------------------------------- */
    .gs-empty {
        border: 1px dashed var(--gs-line-2); border-radius: var(--gs-radius);
        background: var(--gs-surface-2); padding: 1.4rem 1.2rem; text-align: center;
        color: var(--gs-muted);
    }
    .gs-empty .gs-empty-icon { font-size: 1.5rem; display: block; margin-bottom: 0.4rem; }
    .gs-empty strong { color: var(--gs-ink); display: block; margin-bottom: 0.2rem; font-size: 0.97rem; }
    .gs-empty .gs-empty-body { font-size: 0.87rem; }
    .gs-empty.flat { border: none; background: transparent; padding: 0.9rem 0.4rem; }

    /* --- Findings and checks --------------------------------------------- */
    .gs-finding {
        border-radius: var(--gs-radius-xs); padding: 0.55rem 0.8rem;
        margin: 0.3rem 0; border-left: 3px solid var(--gs-line-2);
        background: var(--gs-surface-2); color: var(--gs-ink-2);
        font-size: 0.9rem;
    }
    .gs-finding.error { border-left-color: var(--gs-stop); background: var(--gs-stop-bg); }
    .gs-finding.warning { border-left-color: #d69a2b; background: var(--gs-warn-bg); }
    .gs-finding.info { border-left-color: var(--gs-brand-2); background: var(--gs-info-bg); }
    .gs-check {
        display: flex; gap: 0.65rem; padding: 0.55rem 0.1rem;
        border-bottom: 1px solid var(--gs-line);
    }
    .gs-check:last-child { border-bottom: none; }
    .gs-check-icon { flex-shrink: 0; }
    .gs-check-label { font-weight: 650; color: var(--gs-ink); font-size: 0.92rem; }
    .gs-check-detail { color: var(--gs-muted); font-size: 0.86rem; }

    /* Scope signals and model notes, rendered inside a panel body. */
    .gs-signal {
        border-left: 3px solid var(--gs-line-2);
        background: var(--gs-surface-2);
        border-radius: 0 var(--gs-radius-xs) var(--gs-radius-xs) 0;
        padding: 0.5rem 0.7rem; margin-bottom: 0.45rem;
        font-size: 0.88rem; color: var(--gs-ink); line-height: 1.5;
    }
    .gs-signal:last-child { margin-bottom: 0; }
    .gs-signal--error { border-left-color: var(--gs-stop); background: var(--gs-stop-bg); }
    .gs-signal--warning { border-left-color: var(--gs-warn); background: var(--gs-warn-bg); }
    .gs-signal--info { border-left-color: var(--gs-info); background: var(--gs-info-bg); }
    .gs-note-h {
        font-size: 0.74rem; font-weight: 700; letter-spacing: 0.05em;
        text-transform: uppercase; color: var(--gs-muted);
        margin: 0.7rem 0 0.3rem;
    }
    .gs-note-h:first-child { margin-top: 0; }

    [data-testid="stHorizontalBlock"] { align-items: stretch; }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: var(--gs-radius); border: 1px solid var(--gs-line);
        background: var(--gs-surface); padding: 0.6rem 0.75rem;
        box-shadow: var(--gs-shadow-sm);
    }
    div[data-testid="stForm"] {
        border-radius: var(--gs-radius); border: 1px solid var(--gs-line);
        background: var(--gs-surface); padding: 1.1rem 1.2rem;
        box-shadow: var(--gs-shadow-sm);
    }
    div[data-testid="stExpander"] details {
        border: 1px solid var(--gs-line); border-radius: var(--gs-radius-sm);
        background: var(--gs-surface); box-shadow: var(--gs-shadow-sm);
    }
    /* Streamlit's expander chevron is a Material Symbols *ligature*: the literal
       word "keyboard_arrow_right" is the glyph, and the icon webfont is not
       always reachable (offline, blocked CDN). Combined with the font override
       above, that word rendered as visible text on top of the expander label and
       widened the row. The ligature is removed entirely and replaced with a
       CSS-drawn chevron inside a fixed-size box, so it works either way and
       contributes no width. */
    span[data-testid="stIconMaterial"] {
        display: none;
        font-family: initial !important;
    }
    div[data-testid="stExpander"] summary > span:first-child {
        position: relative;
        display: inline-flex; align-items: center; justify-content: center;
        width: 1.15rem; height: 1.15rem; flex-shrink: 0;
    }
    div[data-testid="stExpander"] summary > span:first-child::after {
        content: ""; position: absolute; left: 50%; top: 50%;
        width: 7px; height: 7px; margin: -5px 0 0 -4px;
        border-right: 2px solid var(--gs-muted);
        border-bottom: 2px solid var(--gs-muted);
        transform: rotate(-45deg);
        transition: transform 0.15s ease;
    }
    div[data-testid="stExpander"] details[open] summary > span:first-child::after {
        transform: rotate(45deg);
    }
    div[data-testid="stExpander"] summary { cursor: pointer; }
    div[data-testid="stAlert"] {
        border-radius: var(--gs-radius-sm); border: 1px solid var(--gs-line);
        box-shadow: none;
    }
    div[data-testid="stMetric"] {
        background: var(--gs-surface); border: 1px solid var(--gs-line);
        border-radius: var(--gs-radius-sm); padding: 0.8rem 0.95rem;
        box-shadow: var(--gs-shadow-sm);
    }
    /* --- Tabs ----------------------------------------------------------- */
    div[data-testid="stTabs"] { gap: 0.2rem; }
    div[data-testid="stTab"] {
        font-weight: 650; color: var(--gs-muted);
        padding: 0.55rem 0.8rem;
        border-bottom: 2px solid transparent;
    }
    div[data-testid="stTab"]:hover { color: var(--gs-brand-ink); }
    div[data-testid="stTab"][aria-selected="true"] {
        color: var(--gs-brand-ink);
        border-bottom-color: var(--gs-brand);
    }

    /* --- Buttons --------------------------------------------------------- */
    div.stButton > button, div.stFormSubmitButton > button,
    button[data-testid="stBaseButton-secondary"],
    button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-primaryFormSubmit"] {
        border-radius: var(--gs-radius-xs); font-weight: 600;
        min-height: 2.45rem;
        /* Let a long label wrap instead of collapsing to "C...". */
        white-space: normal; height: auto; line-height: 1.25;
        padding-top: 0.45rem; padding-bottom: 0.45rem;
        transition: transform 0.08s ease, box-shadow 0.12s ease,
                    border-color 0.12s ease, background 0.12s ease;
    }
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {
        border-color: var(--gs-brand-2); color: var(--gs-brand-ink);
    }
    div.stButton > button[kind="primary"],
    div.stFormSubmitButton > button[kind="primary"],
    button[data-testid="stBaseButton-primary"] {
        background: var(--gs-brand); border: 1px solid var(--gs-brand);
        color: #ffffff; box-shadow: var(--gs-shadow-accent);
    }
    /* Streamlit renders a form submit button as its own kind. */
    div.stFormSubmitButton > button[kind="primaryFormSubmit"],
    button[data-testid="stBaseButton-primaryFormSubmit"] {
        background: var(--gs-brand); border: 1px solid var(--gs-brand);
        color: #ffffff; box-shadow: var(--gs-shadow-accent);
    }
    div.stButton > button[kind="primary"]:hover,
    div.stFormSubmitButton > button[kind="primary"]:hover,
    div.stFormSubmitButton > button[kind="primaryFormSubmit"]:hover,
    button[data-testid="stBaseButton-primary"]:hover,
    button[data-testid="stBaseButton-primaryFormSubmit"]:hover {
        color: #ffffff; background: #6242d8;
        border-color: #6242d8;
    }
    div.stButton > button[kind="secondary"],
    button[data-testid="stBaseButton-secondary"] {
        background: var(--gs-surface); border: 1px solid var(--gs-line-2);
        color: var(--gs-ink-2);
    }
    /* Streamlit truncates a long button label to "C..."; let it wrap instead. */
    div.stButton > button [class*="stMarkdownEllipsis"],
    div.stButton > button [class*="stMarkdownEllipsis"] p {
        overflow: visible !important;
        text-overflow: clip !important;
        white-space: normal !important;
        line-height: 1.25;
    }

    /* --- Segmented control (role switch and section jump) --------------- */
    div[data-testid="stButtonGroup"] {
        display: inline-flex;
        background: var(--gs-surface-3);
        border: 1px solid var(--gs-line);
        border-radius: 999px;
        padding: 3px;
        gap: 2px;
    }
    div[data-testid="stButtonGroup"] button[role="radio"] {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        color: var(--gs-muted) !important;
        font-weight: 600 !important;
        font-size: 0.84rem;
        border-radius: 999px !important;
        min-height: 1.85rem;
        padding: 0.2rem 0.85rem;
        white-space: nowrap;
    }
    div[data-testid="stButtonGroup"] button[role="radio"]:hover {
        background: rgba(115, 83, 232, 0.1) !important;
        color: var(--gs-brand-ink) !important;
    }
    div[data-testid="stButtonGroup"] button[role="radio"][aria-selected="true"],
    div[data-testid="stButtonGroup"] button[role="radio"][aria-checked="true"] {
        background: #ffffff !important;
        color: var(--gs-brand-ink) !important;
        box-shadow: 0 2px 8px rgba(70, 50, 150, 0.13) !important;
    }

    /* --- Inputs ---------------------------------------------------------- */
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stTextArea"] textarea,
    div[data-baseweb="select"] > div {
        border-radius: var(--gs-radius-xs) !important;
        border-color: var(--gs-line-2) !important;
        background: #ffffff !important;
    }
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stTextArea"] textarea:focus {
        border-color: var(--gs-brand-2) !important;
        box-shadow: 0 0 0 3px rgba(165, 138, 244, 0.22) !important;
    }
    /* Keep every accent-coloured control on the brand colour rather than
       Streamlit's default red. */
    [data-baseweb="radio"] input:checked + div,
    [data-baseweb="checkbox"] input:checked + div {
        background-color: var(--gs-brand) !important;
        border-color: var(--gs-brand) !important;
    }
    [data-baseweb="radio"] > div:first-child,
    [data-baseweb="checkbox"] > div:first-child {
        border-color: var(--gs-line-2) !important;
    }
    [data-baseweb="slider"] [role="slider"],
    [data-baseweb="slider"] div[role="slider"] {
        background-color: var(--gs-brand) !important;
    }
    [data-testid="stProgress"] > div > div > div { background-color: var(--gs-brand); }
    label, div[data-testid="stWidgetLabel"] p {
        font-weight: 600; color: var(--gs-ink-2); font-size: 0.9rem;
    }
    hr { border-color: var(--gs-line); }

    /* A quiet "back to start" link, used under the breadcrumb. */
    div.st-key-back_to_landing button,
    div.st-key-student_back_to_landing button {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        color: var(--gs-muted) !important;
        min-height: 1.5rem !important;
        padding: 0 !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        width: auto !important;
        justify-content: flex-start;
    }
    div.st-key-back_to_landing button:hover,
    div.st-key-student_back_to_landing button:hover {
        color: var(--gs-brand-ink) !important;
    }

    /* --- Narrow screens -------------------------------------------------- */
    @media (max-width: 1200px) {
        /* The header keeps breadcrumb, workspace context, and the primary action.
           Tighter spacing, never a hidden control or a larger title. */
        [data-testid="stMainBlockContainer"] { padding: 0.9rem 1.1rem 2rem; }
    }
    @media (max-width: 980px) {
        div[data-testid="stButtonGroup"] button[role="radio"] {
            padding: 0.2rem 0.5rem;
            font-size: 0.76rem;
        }
        /* Only on a genuinely narrow window does the workspace chip step aside;
           the breadcrumb and the primary action always remain. */
        .gs-profile, .gs-no-profile { display: none; }
        .gs-display { font-size: 1.45rem; }
    }
</style>
"""


def inject_styles() -> None:
    """Add Gigsie's shared stylesheet to the page."""
    st.markdown(_FONT_CSS, unsafe_allow_html=True)
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Small HTML helpers
# ---------------------------------------------------------------------------
def esc(value: Any) -> str:
    """HTML-escape any value for safe interpolation."""
    return _escape("" if value is None else str(value))


def _txt(value: Any) -> str:
    """Escape markup-significant characters in a *static* product label.

    Headings and captions are written by this product, never by a user, so an
    ampersand in "Applicants & interviews" must stay readable in the text itself
    rather than turning into an entity. Only ``<`` and ``>`` are escaped here;
    anything coming from stored data goes through :func:`esc` instead.
    """
    return str(value).replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
def current_view() -> str:
    return st.session_state.get("view", VIEW_HOME)


def current_section() -> str:
    return st.session_state.get("section", SEC_OVERVIEW)


def go(view: str, section: str = SEC_OVERVIEW) -> None:
    """Switch the active page and rerun."""
    st.session_state["view"] = view
    st.session_state["section"] = section
    st.rerun()


def nav_sidebar() -> None:
    """Permanent sidebar: wordmark, grouped navigation, prototype footer."""
    with st.sidebar:
        st.markdown(
            '<div class="gs-wordmark">'
            '<span class="gs-brand-mark">◆</span>'
            f"<span>Gig<em>sie</em></span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="gs-brand-sub">{esc(PRODUCT_DESCRIPTOR)}</div>',
            unsafe_allow_html=True,
        )

        view = current_view()
        section = current_section()
        for group, items in NAV_GROUPS:
            st.markdown(
                f'<div class="gs-nav-label">{esc(group)}</div>', unsafe_allow_html=True
            )
            for item_view, item_section, icon, label in items:
                active = view == item_view and section == item_section
                if st.button(
                    f"{icon}   {label}",
                    key=f"nav_{item_view}_{item_section or 'root'}",
                    use_container_width=True,
                    type="primary" if active else "secondary",
                ) and not active:
                    go(item_view, item_section)

        st.markdown(
            '<div class="gs-sidebar-foot">Local prototype &middot; everything is stored '
            "on this device only.<br>No accounts, payments, messaging, or video calls.</div>",
            unsafe_allow_html=True,
        )


def top_header(
    *,
    crumb: list[str] | None = None,
    role: str = ROLE_BUSINESS,
    search: bool = False,
    search_key: str = "gs_search",
    search_placeholder: str = "Search saved gigs",
    profile_name: str = "",
    profile_sub: str = "",
    profile_avatar: str = "",
    primary_label: str = "",
    primary_target: tuple[str, str] | None = None,
    primary_key: str = "gs_header_primary",
    back_key: str = "",
) -> None:
    """Compact top header: breadcrumb, profile context, one primary action.

    The sidebar is the permanent navigation, so the header deliberately carries
    **no** second navigation control: there is no "back to start" link and no
    Business/Student switch, because both duplicated a destination the sidebar
    already shows on every page. ``back_key`` is accepted and ignored so callers
    do not have to change.

    The search field is only rendered on list pages, where it really filters the
    locally saved gigs. Nothing here is decorative - every control navigates.
    """
    del role, back_key  # Navigation lives in the sidebar only.

    where, who, action = st.columns([3.2, 1.7, 1.6], gap="small", vertical_alignment="center")

    with where:
        parts = []
        for index, part in enumerate(crumb or []):
            tag = "b" if index == len(crumb) - 1 else "span"
            parts.append(f"<{tag}>{_txt(part)}</{tag}>")
        st.markdown(
            '<div class="gs-crumb">' + "<span>/</span>".join(parts) + "</div>",
            unsafe_allow_html=True,
        )

    with who:
        if profile_name:
            initial = _txt(profile_avatar or (str(profile_name)[:1].upper() or "?"))
            st.markdown(
                '<div class="gs-profile">'
                f'<span class="gs-avatar">{initial}</span>'
                "<span>"
                f'<div class="gs-profile-name">{_txt(profile_name)}</div>'
                f'<div class="gs-profile-sub">{_txt(profile_sub)}</div>'
                "</span></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="gs-no-profile">No profile saved</div>',
                unsafe_allow_html=True,
            )

    with action:
        if primary_label and primary_target:
            if st.button(
                primary_label,
                key=primary_key,
                type="primary",
                use_container_width=True,
            ):
                go(*primary_target)

    # The search sits on its own full-width row so it can filter real records
    # without squeezing the rest of the header on a narrow window.
    if search:
        st.text_input(
            "Search",
            key=search_key,
            placeholder=search_placeholder,
            label_visibility="collapsed",
        )

    st.markdown('<div class="gs-top-rule"></div>', unsafe_allow_html=True)


def header_rule() -> None:
    """A thin divider used between stacked sections."""
    st.markdown(
        '<div style="height:1px;background:var(--gs-line);margin:1.1rem 0 1.3rem"></div>',
        unsafe_allow_html=True,
    )


def search_query(key: str, items: list[str], empty_text: str = "") -> str:
    """Read the header search box and return it, or an inline note when empty."""
    query = str(st.session_state.get(key) or "").strip()
    if not items:
        return ""
    if not query:
        return ""
    hits = [item for item in items if query.lower() in item.lower()]
    if not hits and empty_text:
        st.caption(empty_text)
    return query


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------
def eyebrow(text: str) -> None:
    """A small uppercase label above a heading."""
    st.markdown(f'<div class="gs-eyebrow">{_txt(text)}</div>', unsafe_allow_html=True)


def display_title(active: str, *muted: str) -> None:
    """A large display heading with muted trailing words (reference style)."""
    tail = "".join(f' <span class="off">{_txt(word)}</span>' for word in muted)
    st.markdown(
        f'<h1 class="gs-display">{_txt(active)}{tail}</h1>', unsafe_allow_html=True
    )


def page_header(
    title: str,
    subtitle: str = "",
    eyebrow_text: str = "",
    title_html: str = "",
) -> None:
    """Render a page header: optional eyebrow, title, and subtitle."""
    parts = ['<div class="gs-page-head">']
    if eyebrow_text:
        parts.append(f'<div class="gs-eyebrow">{_txt(eyebrow_text)}</div>')
    if title_html:
        parts.append(f'<h1 class="gs-page-title">{title_html}</h1>')
    else:
        parts.append(f'<h1 class="gs-page-title">{_txt(title)}</h1>')
    if subtitle:
        parts.append(f'<p class="gs-page-sub">{_txt(subtitle)}</p>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def section_heading(title: str, caption: str | None = None) -> None:
    """Render a consistent section heading with an optional caption."""
    st.markdown(f'<div class="gs-section-title">{_txt(title)}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(
            f'<div class="gs-section-caption">{_txt(caption)}</div>', unsafe_allow_html=True
        )


def hero(
    badge: str = "Local-first prototype · no accounts, no payments",
    title: str = "Gigsie",
    subtitle: str = TAGLINE,
) -> None:
    """Render the gradient hero banner."""
    badge_html = f'<span class="gigsie-badge">{_txt(badge)}</span>' if badge else ""
    st.markdown(
        f'<div class="gigsie-hero"><h1>{_txt(title)}</h1>'
        f"<p>{_txt(subtitle)}</p>{badge_html}</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Cards and panels
# ---------------------------------------------------------------------------
def stat_card(label: str, value: str, hint: str = "", tone: str = "") -> None:
    """A metric tile: label, the real number, and an honest hint."""
    hint_html = f'<div class="gs-stat-hint">{_txt(hint)}</div>' if hint else ""
    tone_cls = f" tone-{_txt(tone)}" if tone else ""
    st.markdown(
        f'<div class="gs-stat{tone_cls}">'
        f'<div class="gs-stat-label">{_txt(label)}</div>'
        f'<div class="gs-stat-value">{_txt(value)}</div>'
        f"{hint_html}</div>",
        unsafe_allow_html=True,
    )


def panel(
    title: str,
    caption: str = "",
    body: str = "",
    tags: str = "",
    footer: str = "",
    accent: str = "",
    kebab: bool = False,
    fill: bool = False,
) -> None:
    """A bordered card with a title row, body, tag row, and footer.

    ``body`` is pre-escaped-safe HTML built by the caller. Nothing is invented:
    an empty ``body`` simply renders an empty card body. ``fill`` stretches the
    card to the tallest column so a grid row lines up.
    """
    caption_html = f'<div class="gs-panel-caption">{_txt(caption)}</div>' if caption else ""
    kebab_html = '<span class="gs-kebab">···</span>' if kebab else ""
    body_html = f'<div class="gs-panel-body">{body}</div>' if body else ""
    tags_html = f'<div class="gs-panel-foot">{tags}</div>' if tags else ""
    footer_html = f'<div class="gs-panel-foot">{footer}</div>' if footer else ""
    accent_cls = f" {accent}" if accent else ""
    fill_cls = " gs-panel--fill" if fill else ""
    st.markdown(
        f'<div class="gs-panel{accent_cls}{fill_cls}">'
        f'<div class="gs-panel-head"><div><div class="gs-panel-title">{_txt(title)}</div>'
        f"{caption_html}</div>{kebab_html}</div>{body_html}{tags_html}{footer_html}</div>",
        unsafe_allow_html=True,
    )


def module_card(
    title: str,
    caption: str,
    body: str,
    tags: str = "",
    action: str = "",
    fill: bool = False,
) -> None:
    """Reference module card: title, muted caption, body text, divider, tags."""
    tags_html = (
        f'<div class="gs-panel-foot">{tags}</div>' if tags else ""
    )
    action_html = (
        f'<div style="margin-top:.55rem">{action}</div>' if action else ""
    )
    fill_cls = " gs-panel--fill" if fill else ""
    st.markdown(
        f'<div class="gs-panel{fill_cls}"><div class="gs-panel-head"><div>'
        f'<div class="gs-panel-title">{_txt(title)}</div>'
        f'<div class="gs-panel-caption">{_txt(caption)}</div>'
        f'</div><span class="gs-kebab">···</span></div>'
        f'<div class="gs-panel-body" style="margin-top:.75rem">{body}</div>'
        f"{tags_html}{action_html}</div>",
        unsafe_allow_html=True,
    )


def info_card(title: str, body: str, accent: str = "brand", icon: str = "") -> None:
    """A static informational card."""
    cls = "gs-card--accent" if accent == "accent" else "gs-card--brand"
    icon_html = f'<span class="gs-card-icon">{esc(icon)}</span>' if icon else ""
    st.markdown(
        f'<div class="gs-card {cls}">{icon_html}<h4>{_txt(title)}</h4><p>{_txt(body)}</p></div>',
        unsafe_allow_html=True,
    )


def empty_state(icon: str, title: str, body: str, flat: bool = False) -> None:
    """A friendly empty state. Guidance only - never invented data."""
    cls = "gs-empty flat" if flat else "gs-empty"
    st.markdown(
        f'<div class="{cls}"><span class="gs-empty-icon">{_txt(icon)}</span>'
        f"<strong>{_txt(title)}</strong>"
        f'<span class="gs-empty-body">{_txt(body)}</span></div>',
        unsafe_allow_html=True,
    )


def list_rows(rows: list[str]) -> str:
    """Build the ``.gs-list`` markup for a list of already-escaped row strings."""
    if not rows:
        return ""
    return '<ul class="gs-list">' + "".join(f"<li>{row}</li>" for row in rows) + "</ul>"


def bullets(items: Any) -> str:
    """Build bullet markup from real values."""
    values = [str(item).strip() for item in items if str(item).strip()] if isinstance(
        items, (list, tuple)
    ) else []
    if not values:
        return '<div class="gs-note">None listed.</div>'
    return '<ul class="gs-bullet">' + "".join(f"<li>{esc(v)}</li>" for v in values) + "</ul>"


def key_values(pairs: list[tuple[str, Any]]) -> str:
    """Build a small label/value block from real values."""
    if not pairs:
        return ""
    rows = "".join(
        f'<div class="gs-kv"><span>{esc(label)}</span><b>{esc(value)}</b></div>'
        for label, value in pairs
    )
    return f'<div style="margin-top:.4rem">{rows}</div>'


def data_table(headers: list[str], rows: list[list[str]]) -> None:
    """A compact table built only from real saved records."""
    if not rows:
        return
    head = "".join(f"<th>{esc(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    st.markdown(
        # `overflow-x: auto` rather than hidden: a table has a minimum width, and
        # clipping it would silently drop columns instead of letting the reader
        # scroll to them.
        '<div class="gs-table-wrap">'
        f'<table class="gs-table"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Chips, tags, pills
# ---------------------------------------------------------------------------
def chip(text: str, tone: str = "neutral") -> str:
    """An inline chip. ``tone`` is ok/warn/stop/info/neutral."""
    safe = tone if tone in {"ok", "warn", "stop", "info", "neutral"} else "neutral"
    return f'<span class="gs-chip tone-{safe}">{esc(text)}</span>'


def tag(text: str) -> str:
    """A small neutral tag (skill chips, group tags)."""
    return f'<span class="gs-tag">{esc(text)}</span>'


def tags(values: Any, limit: int = 0) -> str:
    """A row of neutral tags from real values."""
    items = [str(value).strip() for value in values if str(value).strip()] if isinstance(
        values, (list, tuple)
    ) else []
    if limit:
        items = items[:limit]
    return "".join(tag(item) for item in items)


def skill_tags(skills: Any) -> str:
    """A row of soft skill chips, or a muted 'no skills' chip."""
    values = [str(skill) for skill in skills] if isinstance(skills, (list, tuple)) else []
    if not values:
        return chip("No skills listed", "neutral")
    return "".join(chip(value, "info") for value in values)


def status_pill(status: Any, label: Any = None) -> str:
    """Render a status as a colored pill."""
    text = str(label or status or "unknown")
    key = str(status or "neutral").strip().lower().replace(" ", "_")
    return f'<span class="gigsie-pill pill-{key}">{esc(text)}</span>'


def status_pill_html(status: Any, label: Any = None) -> str:
    """Alias kept for readability at call sites."""
    return status_pill(status, label)


def sample_tag() -> str:
    """The inline 'SAMPLE' tag used for illustrative data."""
    return '<span class="gigsie-sample-tag">SAMPLE</span>'


def finding_html(level: str, message: str) -> str:
    """Inline HTML for a validation finding."""
    safe = level if level in {"error", "warning", "info"} else "info"
    return f'<div class="gs-finding {safe}">{esc(message)}</div>'


# ---------------------------------------------------------------------------
# Progress rail
# ---------------------------------------------------------------------------
def step_rail(steps: list[str], active: int) -> None:
    """Render a horizontal progress rail. ``active`` is a 0-based index.

    Orientation only - it never gates a flow.
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
            f'<span class="gs-rail-step {state}"><span class="gs-num">{number}</span>'
            f"{esc(label)}</span>"
        )
    st.markdown('<div class="gs-rail">' + "".join(parts) + "</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# The single source of truth for how a gig reads
# ---------------------------------------------------------------------------
def gig_title(gig: Any) -> str:
    return str((gig or {}).get("title") or "Untitled gig").strip()


def gig_context(gig: Any) -> str:
    return str((gig or {}).get("business_name") or "Independent request").strip()


def gig_budget(gig: Any) -> str:
    """Readable budget. Never guesses a number."""
    budget = (gig or {}).get("budget_inr")
    try:
        if budget in (None, "", 0, 0.0):
            return "Budget not set"
        return f"{float(budget):,.0f} INR"
    except (TypeError, ValueError):
        return "Budget not set"


def gig_deadline(gig: Any) -> str:
    return str((gig or {}).get("deadline") or "No deadline")


def gig_objective(gig: Any) -> str:
    gig = gig or {}
    brief = gig.get("brief") if isinstance(gig.get("brief"), dict) else {}
    return str(
        gig.get("objective")
        or brief.get("objective")
        or brief.get("project_objective")
        or gig.get("desired_outcome")
        or ""
    ).strip()


def gig_skills(gig: Any) -> list[str]:
    return validation.get_required_skills(gig)


def gig_deliverables(gig: Any) -> list[str]:
    return validation.get_deliverables(gig)


def gig_acceptance(gig: Any) -> list[str]:
    brief = (gig or {}).get("brief") if isinstance((gig or {}).get("brief"), dict) else {}
    value = brief.get("acceptance_criteria")
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def gig_badge(gig: Any) -> str:
    """Sample gigs always stay labelled SAMPLE; real gigs show their status."""
    if (gig or {}).get("sample"):
        return sample_tag()
    status = str((gig or {}).get("status") or "open")
    return chip(status.title(), "ok" if status == "open" else "neutral")


def gig_meta_row(gig: Any, right: str = "") -> str:
    """The small meta line at the top of a gig card (reference job-card row)."""
    left = gig_badge(gig)
    if (gig or {}).get("sample"):
        left += chip("Example data", "neutral")
    tail = f'<span class="kebab">⋮</span>' if not right else f"<span>{esc(right)}</span>"
    return f'<div class="gs-job-top"><span>{left}</span><span class="kebab">{tail}</span></div>'


def gig_card(
    gig: dict[str, Any],
    *,
    description: str = "",
    meta_right: str = "",
    match_line: str = "",
    fill: bool = False,
) -> str:
    """The shared gig card markup used on every page.

    One function, one source of truth: the title, context, budget, deadline, and
    skills read identically on the business dashboard, the published list, the
    student browse grid, the gig detail page, and application review.
    """
    body = description or gig_objective(gig) or "No outcome described yet."
    match_html = f'<div class="gs-job-match">{match_line}</div>' if match_line else ""
    fill_cls = " gs-job--fill" if fill else ""
    return (
        f'<div class="gs-job{fill_cls}">'
        f"{gig_meta_row(gig, meta_right)}"
        f"<h4>{esc(gig_title(gig))}</h4>"
        f'<div class="gs-job-ctx">{esc(gig_context(gig))}</div>'
        f'<div class="gs-job-text">{esc(body)}</div>'
        f"{match_html}"
        f'<div class="gs-job-tags">{tags(gig_skills(gig), limit=6)}</div>'
        '<div class="gs-job-foot">'
        f'<span class="gs-money">{esc(gig_budget(gig))}</span>'
        f'<span class="gs-job-meta">Due {esc(gig_deadline(gig))}</span>'
        "</div></div>"
    )


def gig_row(gig: dict[str, Any], trailing: str = "") -> str:
    """A compact one-line gig row for side panels."""
    return (
        f'<div><b>{esc(gig_title(gig))}</b>'
        f'<div class="muted">{esc(gig_context(gig))} · {esc(gig_budget(gig))}</div></div>'
        f'<div>{gig_badge(gig)}{trailing}</div>'
    )


def gig_grid(cards: list[str], per_row: int = 2) -> None:
    """Lay pre-rendered gig cards out in real rows.

    Each row is its own column group, so the equal-height rule applies within a
    row. Filling two long columns instead would let a lone card stretch to the
    height of a stack of cards in the neighbouring column.
    """
    for start in range(0, len(cards), per_row):
        columns = st.columns(per_row, gap="medium")
        for offset, html in enumerate(cards[start : start + per_row]):
            with columns[offset]:
                st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Findings, lists, passport
# ---------------------------------------------------------------------------
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


def bullet_list(items: Any, empty_text: str = "None.") -> None:
    """Render a list of items as markdown bullets, or a caption when empty."""
    values = [str(item) for item in items] if isinstance(items, (list, tuple)) else []
    if not values:
        st.caption(empty_text)
        return
    for item in values:
        st.markdown(f"- {item}")


def passport_value(section: Any) -> None:
    """Render one Gig Passport section, marking unknown information honestly."""
    if not isinstance(section, dict):
        return
    if section.get("needs_clarification"):
        st.caption("Needs clarification - now shown to students as not yet specified.")
        return
    value = section.get("value")
    if isinstance(value, list):
        values = [str(item) for item in value if str(item).strip()]
        if values:
            for item in values:
                st.markdown(f"- {item}")
        else:
            st.caption("None.")
        return
    text = str(value if value is not None else "").strip()
    if text:
        st.markdown(text)
    else:
        st.caption("None.")


def back_button(label: str = "← Back to start", key: str = "back_to_landing") -> None:
    """Render a back-to-home button."""
    if st.button(label, key=key):
        go(VIEW_HOME, SEC_OVERVIEW)
