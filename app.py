"""Gigsie - Phase 2: Streamlit user interface.

This phase builds the INTERFACE only:
    1. A clear business request form.
    2. Required-input validation (validation.py - plain Python, no AI).
    3. A "Generate Task Brief" button.
    4. A placeholder results section with the headings the brief will use.

The Groq AI integration (gigsie_ai.py) is intentionally NOT called yet. Clicking
the button validates the form and shows a placeholder. AI generation is added next.
"""

from __future__ import annotations

import streamlit as st

from validation import validate_request

TAGLINE = "Turn vague business requests into clear opportunities."

# The sections the finished brief will contain. Shown now as placeholders.
RESULT_SECTIONS = [
    "Project objective",
    "Deliverables",
    "Required skills",
    "Clarifying questions",
    "Acceptance criteria",
    "Assumptions",
    "Scope warnings",
]

# ---------------------------------------------------------------------------
# Page setup and light styling
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Gigsie - Task Brief Generator", page_icon="📝", layout="wide")

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; max-width: 1100px; }
    .gigsie-hero {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        color: #ffffff;
        padding: 1.6rem 1.8rem;
        border-radius: 16px;
        margin-bottom: 1.2rem;
    }
    .gigsie-hero h1 { margin: 0; font-size: 2.1rem; }
    .gigsie-hero p { margin: 0.4rem 0 0; opacity: 0.92; font-size: 1.05rem; }
    .gigsie-badge {
        display: inline-block;
        background: rgba(255,255,255,0.18);
        border-radius: 999px;
        padding: 0.15rem 0.7rem;
        font-size: 0.78rem;
        margin-top: 0.7rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="gigsie-hero">
        <h1>📝 Gigsie</h1>
        <p>{TAGLINE}</p>
        <span class="gigsie-badge">Phase 2 - interface preview</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# The business request form
# ---------------------------------------------------------------------------
with st.form("request_form"):
    st.subheader("Business request")
    st.caption("Fields marked with * are required. Everything else is optional.")

    project_name = st.text_input(
        "Business or project name (optional)",
        placeholder="e.g. Sunrise Bakery",
    )

    description = st.text_area(
        "What work needs to be done? *",
        placeholder="e.g. I want help promoting my new menu.",
        height=90,
    )

    outcome = st.text_area(
        "What outcome does the business want? *",
        placeholder="e.g. More local customers see the menu and visit the shop.",
        height=90,
    )

    col_budget, col_deadline = st.columns(2)
    with col_budget:
        budget = st.number_input(
            "Budget in Indian rupees (INR, optional)",
            min_value=0.0,
            step=100.0,
            value=0.0,
            format="%.0f",
        )
    with col_deadline:
        deadline = st.text_input(
            "Deadline or available number of days (optional)",
            placeholder="e.g. 2 days, or 15 Oct 2026",
        )

    extra_context = st.text_area(
        "Additional information (optional)",
        placeholder="e.g. Target audience, platforms you already use, brand colours.",
        height=80,
    )

    submitted = st.form_submit_button(
        "Generate Task Brief", type="primary", use_container_width=True
    )

# ---------------------------------------------------------------------------
# Handle submission
# ---------------------------------------------------------------------------
if submitted:
    request = {
        "project_name": project_name.strip(),
        "description": description.strip(),
        "outcome": outcome.strip(),
        "budget": budget,
        "deadline": deadline.strip(),
        "extra_context": extra_context.strip(),
    }

    # Plain-Python validation. Errors block progress; no AI is called in this phase.
    errors = [f for f in validate_request(request) if f["level"] == "error"]

    if errors:
        st.error("Please fix the following before generating a brief:")
        for finding in errors:
            st.markdown(f"- {finding['message']}")
        st.session_state.pop("request", None)
    else:
        st.session_state["request"] = request

# ---------------------------------------------------------------------------
# Placeholder results section
# ---------------------------------------------------------------------------
if st.session_state.get("request") is not None:
    request = st.session_state["request"]

    st.divider()
    st.subheader("Task brief")
    st.info(
        "**Nothing has been generated yet.** Clicking **Generate Task Brief** validated your "
        "request. The AI-powered brief will appear in these sections once the Groq "
        "integration is added in the next phase."
    )

    # --- Confirmation of what was captured (not AI output) ---
    budget_text = f"{request['budget']:,.0f} INR" if request["budget"] else "Not provided"
    with st.container(border=True):
        st.markdown("**Request received**")
        col_left, col_right = st.columns(2)
        with col_left:
            st.markdown(f"**Project:** {request['project_name'] or 'Not provided'}")
            st.markdown(f"**Work needed:** {request['description']}")
            st.markdown(f"**Desired outcome:** {request['outcome']}")
        with col_right:
            st.markdown(f"**Budget:** {budget_text}")
            st.markdown(f"**Deadline:** {request['deadline'] or 'Not provided'}")
            st.markdown(f"**Additional information:** {request['extra_context'] or 'Not provided'}")

    # --- The sections the brief will fill in later ---
    st.markdown("#### Generated brief (placeholder)")
    st.caption("These sections will show AI-generated results after the next phase.")

    columns = st.columns(2)
    for index, section in enumerate(RESULT_SECTIONS):
        with columns[index % 2]:
            with st.container(border=True):
                st.markdown(f"**{section}**")
                st.caption("Awaiting AI generation.")
