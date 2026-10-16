# Gigsie — AI-Powered Task Brief Generator

Gigsie helps a small-business owner turn a vague work request into a clear, structured
**draft** task brief that a student or beginner freelancer can understand and pick up.

Example input:

> "I run a bakery and want help promoting my new menu. My budget is ₹800, and I need the
> work completed within two days."

Gigsie turns that into a reviewable brief with an objective, deliverables, required skills,
clarifying questions, acceptance criteria, assumptions, and scope/deadline concerns.

> **The output is a draft for human review.** It is not a hiring decision, a price estimate,
> or a guarantee of results.

> **Current status.** Gigsie is a working local prototype with two connected sides. The
> business side drafts a brief with the Groq-hosted model, reviews it with FairScope
> (deterministic clarity checks + scope signals, kept separate from the model's own
> suggestions), compares three scope strategies, approves an editable **Gig Passport**, and
> publishes explicitly. The student side has local profile onboarding, gig browsing with a
> deterministic skill match, proposals, AI-generated practice assessments graded in Python,
> and interview status. Everything is stored as local JSON on one device: there are **no real
> accounts, authentication, payments, or messaging**, so it is not yet a real multi-user
> marketplace (see "What a real marketplace still needs").

---

## How it works (and why it is split in two)

Gigsie separates the model's job from Python's job on purpose:

| Layer | File | Responsibility |
|---|---|---|
| AI (hosted on Groq) | `gigsie_ai.py` | Understands the request and drafts the brief / revised scope as JSON. |
| Deterministic checks | `validation.py`, `fairscope.py` | Plain Python rules: missing info, scope vs. deadline, clarity checks, scope signals, the Gig Passport. |
| Business logic | `gig_workflow.py` | Form validation, record building, and safe publishing (at most once per draft). |
| Local storage | `storage.py` | Saves and loads gigs, passports, profiles, applications, assessments, interviews from JSON. |
| Student backend | `profiles.py`, `applications.py`, `assessments.py`, `interviews.py` | Profile rules, proposal validation/dedupe/status, Python grading, interview status. |
| Interface & flow | `app.py`, `student_ui.py`, `business_ui.py`, `ui_common.py` | Streamlit screens and the shared visual system. Presentation only. |

- The model does the **language understanding**.
- Python does the **explainable checks**. Findings from Python are labelled
  `deterministic`; model text is labelled as AI output. They are shown separately.
- Gigsie **never** claims a budget is fair, unfair, or sufficient, and never invents market
  prices. It only flags when information is missing or inconsistent.

**Model inference is hosted through Groq.** Nothing runs locally, and the API key is only
read from your local `.env` file — never shown, logged, or written into the code.

---

## Project structure

```
Gigsie/
├── app.py              # Streamlit interface: landing + business flow
├── student_ui.py       # Student area: profile, browse, apply, assessments, interviews
├── business_ui.py      # Business interview loop (applicants, scheduling status)
├── ui_common.py        # Shared design system and small presentation helpers
├── gigsie_ai.py        # Groq integration, prompt, JSON parsing
├── validation.py       # Deterministic validation and the skill matcher (no AI)
├── fairscope.py        # Deterministic scope review + the Gig Passport (no AI, no Streamlit)
├── gig_workflow.py     # Form validation, record building, safe publishing
├── storage.py          # Local JSON persistence for gigs, profiles, applications, ...
├── profiles.py         # Student profiles (local prototype, no accounts)
├── applications.py     # Proposals: validation, dedupe, status lifecycle
├── assessments.py      # Practice assessments: validation and Python grading
├── interviews.py       # Interview status and scheduling details
├── errors.py           # Shared workflow error type
├── tests/              # unittest suite (no real API calls; temporary data dirs)
├── data/               # Local JSON data + labelled sample gigs (git-ignored)
├── requirements.txt    # Python packages
├── README.md           # This file
├── testgroq.py         # Your original Groq connectivity test (untouched)
├── .env                # Your GROQ_API_KEY (never committed)
└── .venv/              # Your virtual environment
```

---

## Setup

1. **Open a terminal in the project folder** (Windows / VS Code).

2. **Activate your virtual environment** (if it is not already active):

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install the dependencies** (already installed in your environment):

   ```powershell
   pip install -r requirements.txt
   ```

   Required packages: `streamlit`, `groq`, `python-dotenv`.

4. **Make sure your `.env` file contains your key** (create it if needed, and keep it out of Git):

   ```
   GROQ_API_KEY=your_key_here
   ```

   `.env` is already listed in `.gitignore`, so it will not be committed.

5. **Optional — confirm your key works:**

   ```powershell
   python testgroq.py
   ```

---

## Run the app

```powershell
streamlit run app.py
```

Streamlit opens `http://localhost:8501` in your browser.

**What to expect:**

Business side (left navigation → Business):
1. Describe the task. Budget and deadline are required so the scope can be reviewed against them.
2. Gigsie asks the model for one real brief, then shows the editor.
3. **FairScope** shows deterministic clarity checks and scope signals, kept separate from the
   model's own suggestions, plus a recommended next action.
4. Optionally generate one **scope strategy** (Budget-first / Outcome-first / Milestone-first) and
   compare it with the current draft. Nothing is replaced or published until you choose it.
5. Edit the brief, resolve or explicitly acknowledge anything still marked **Needs clarification**
   in the **Gig Passport**.
6. Click **Publish gig** to save it. Published gigs appear under "Saved gigs".

Student side (left navigation → Student):
1. Create or load a local profile. The **profile checklist** shows which required basics are
   missing.
2. **Browse gigs** - each card shows the expected work, budget, deadline, and required skills; the
   detail view shows a deterministic skill match and exactly which required skills you do or do
   not list.
3. Write and review a proposal, then submit. Each profile can apply to a gig once.
4. Practice assessments and interview status are optional and never block applying.

The Streamlit UI, FairScope review, Gig Passport, strategies, student profile, proposals,
assessments, and interviews are all implemented and covered by the test suite. State inference
(the brief and strategy revisions, and practice-assessment questions) runs through the Groq-hosted
model and needs internet access.

---

## Testing

The test suite uses synthetic requests and temporary data directories only. It never calls the
real model (the AI functions are mocked) and never touches your local `data/` files.

```powershell
# Full suite (recommended)
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Compile check
.\.venv\Scripts\python.exe -m py_compile app.py gigsie_ai.py validation.py
```

Verified behaviours:
- Valid JSON, JSON in code fences, and JSON surrounded by extra text all parse correctly.
- Malformed and empty responses raise a clean, user-friendly error instead of crashing.
- Missing fields in the model output are reported, not silently dropped.
- Deterministic checks flag missing info and "many deliverables in a short deadline".
- FairScope clarity checks, scope signals, strategies, and Gig Passport gating are covered.
- The business flow, student profile/proposal flow, assessments, and interviews are exercised
  end-to-end through `streamlit.testing.v1.AppTest`.

If the API is unavailable or the key is missing, Gigsie reports the actual error message
rather than pretending to succeed.

---

## Limitations and honest notes

- AI output can vary between runs. Gigsie prefers Groq's JSON mode, but the model can still
  occasionally return something unexpected; the app handles that gracefully and asks you to try again.
- The deterministic checks are simple heuristics (documented in `validation.py` and
  `fairscope.py`). They prompt a human to think — they are not rules about productivity or price.
  A flagged scope is a reason to review, not proof that a task is impossible.
- Gigsie does not verify facts, estimate market rates, or guarantee any outcome. It never invents
  budgets, prices, deliverables, skills, or business facts; missing information is marked
  **Needs clarification**.
- Student skills are **self-reported** and never verified. Match scores are computed in Python and
  are a prompt to read the gig, not a judgement about a person.
- Practice assessments are **AI-generated practice**, graded locally in Python. They are not a
  certification and never block applying.
- Interview coordination is only the stored status: Gigsie does not host video calls, send emails
  or calendar invites, or provide messaging.
- All data is local JSON on one device. Multiple people "using" Gigsie on different machines do
  not share a marketplace.

---

## What a real marketplace still needs

Gigsie is honest about being a local prototype. Making the two sides a real multi-user marketplace
would require, at minimum:

- **A shared database** (not local JSON) so a gig published by one device is visible to students on
  another, and applications/interviews are shared.
- **Real authentication and authorisation**, so a business can only edit its own gigs and a student
  can only see and act on their own applications.
- **Background processing / notifications** for publishing, application status changes, and
  interview coordination (email or in-app), rather than requiring both sides to open the same file.
- **Payments, contracts, and verified identity** before any money or commitment changes hands.
- **Server-side model calls with rate limits and cost controls**, instead of a local API key.

Until those exist, treat everything here as a single-device demonstration.

---

## FairScope and the Gig Passport (Stage 6)

FairScope is a deterministic scope reviewer that sits between the first draft and
publishing. The rule it follows:

> **The AI drafts. Python checks. The business decides. Both sides understand the
> work before it begins.**

`fairscope.py` (no AI, no network, no Streamlit) adds three things:

1. **Clarity check** - plain-Python checks for a specific objective, concrete
   deliverables, measurable acceptance criteria, relevant skills, clear scope
   boundaries, and unanswered questions.
2. **Scope signals** - deterministic warnings such as a broad request with no
   boundary, too many deliverables, missing client assets/access, unclear
   revisions, or acceptance criteria that cannot be checked objectively. These are
   always labelled `deterministic` and kept separate from the model's own notes.
3. **Recommended next action** - a short, prioritised list of what to clarify. No
   numeric feasibility score is produced, and a budget is never called "fair".

**Three scope strategies** (Budget-first, Outcome-first, Milestone-first) are
available as an explicit choice. Selecting one calls the model **once** to revise
the current draft; the original is never replaced or published automatically, and
the original budget and deadline are preserved. A failed revision keeps the
existing draft and shows a useful error.

The **Gig Passport** is an editable summary of the agreed scope (objective,
deliverables, definition of done, included work, exclusions, required skills,
client responsibilities, revision expectations, open questions, assumptions,
budget/deadline, and scope warnings). Missing information is never invented - it
is marked **Needs clarification** and the owner must resolve or explicitly
acknowledge it before publishing. The passport is saved with the gig and shown to
students, so both sides read the same scope.

Schema note: published gigs now carry a top-level `passport` object alongside the
existing `brief`. Older gigs and the labelled samples have no stored passport;
the student view derives one from their brief, so nothing breaks.

---

## One coherent UI: Gigsie Scope Studio (Stage 7)

Stage 7 turned the separate forms into one workspace with a single visual system
(`ui_common.py`): shared colours, typography, spacing, cards, chips, status pills, empty states,
and a persistent Home / Business / Student navigation. The product identity is consistent across
the business and student sides, and each screen has one clear primary action.

FairScope is the signature feature and is visible in the real workflow, not only in `fairscope.py`:

1. Describe the task.
2. Generate the actual AI task brief.
3. Review deterministic clarity checks and separately labelled AI suggestions.
4. Compare Budget-first / Outcome-first / Milestone-first.
5. Review and edit the proposed changes.
6. Approve the Gig Passport (resolve or explicitly acknowledge missing essentials).
7. Publish explicitly.

The business editor and the student view both read the same saved Gig Passport, and the original
budget and deadline are preserved unless the owner explicitly changes them.

---

## Safety

- Never commit `.env`. It is already ignored by `.gitignore`.
- The API key is read only inside `gigsie_ai.py` and is never printed or returned.
- Inference runs on Groq's servers; no local models are downloaded.
