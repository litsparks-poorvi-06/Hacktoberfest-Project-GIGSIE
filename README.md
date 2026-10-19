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
├── .env.example        # Placeholder keys for local setup (safe to commit)
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

   `.env` is already listed in `.gitignore`, so it will not be committed. A safe template with
   placeholders only is in `.env.example`; copy it if you prefer:

   ```powershell
   Copy-Item .env.example .env
   ```

6. **Optional — confirm your key works:**

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

The sidebar is the only navigation. Every destination is its own page.

Business side (*For businesses*):

1. **Create with AI** — describe the task. Budget and deadline are required so the scope can be
   reviewed against them. Gigsie asks the model for one real brief and then opens the review.
2. **FairScope review** (still on the Create with AI page) — deterministic clarity checks and scope
   signals, kept separate from the model's own suggestions, plus a recommended next action.
3. Optionally generate one **scope strategy** (Budget-first / Outcome-first / Milestone-first) and
   compare it with the current draft. Nothing is replaced or published until you choose it.
5. **Gig Passport** — its own page. Edit the brief, resolve or explicitly acknowledge anything still
   marked **Needs clarification**, then click **Publish gig** to save it.
6. **Published Gigs** — everything saved on this device, with search, status, budget, and deadline.
   Labelled samples are listed last and marked **SAMPLE**.
7. **Applicants & Interviews** — its own page: real applications grouped by gig, with the saved
   proposal, profile details, and shortlist / reject / interview-request actions.

Student side (*For students*):

1. **Student Overview** — the real profile state, saved applications, interview responses awaiting
   a reply, and assessment history when they exist. No invented percentages.
2. **My Profile** — create or edit the local profile; the checklist shows which basics are missing.
3. **Find Work** — marketplace-style gig cards with title, outcome, budget, deadline, required
   skills, the published/SAMPLE label, and a real skill match. The detail view shows the same
   Gig Passport the business approved. Write, review, and
   submit a proposal.
4. **My Applications** — submitted proposals and their stored status.
5. **Skill Assessments** and **Interviews** — secondary pages; neither is required before applying.

The Streamlit UI, FairScope review, Gig Passport, strategies, student profile, proposals,
inference (the brief and strategy revisions, and practice-assessment questions) runs through the
and is entirely optional.

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
- Every sidebar destination renders its own real page and each one is clicked through in a test.
  handling, HTTP failure, timeout, **no request before the user asks**, no duplicate request on an
  ordinary rerun, cache invalidation when the text/voice/model changes, narration built from the
  real saved fields, and the core app working with no credentials at all.

mocked at the function boundary; both real `.env` values are never read by the tests.

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
  scope. The saved brief and Gig Passport remain the source of truth, and no audio is ever saved to
  disk.
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

**Strategy identity is state, not a label.** `gigsie_ai.generate_task_brief`
records the strategy it was asked for in `result["scope_strategy"]`. Gigsie stores
that response in `st.session_state["scope_variant"]` and the key the business
actually selected in `st.session_state["scope_variant_key"]`. The comparison
heading, the accept action, and the published passport all read through one
resolver, `_variant_strategy()`, so Budget-first always reads *Budget-first*. (An
earlier build read a non-existent `strategy` key and therefore showed
*Proposed: Unknown strategy*; that is fixed and covered by a regression test for
all three strategies, including accept, discard, failed generation, and reruns.)
Discarding or accepting a proposal clears both keys, and "Start a new brief"
clears them too, so a stale identity can never leak into the next draft.

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

## One coherent UI: Gigsie (Stage 7)

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

## Sample gigs and end-to-end alignment (Stage 8)

Stage 8 made the product one coherent story from the business request to the student proposal.

**Labelled sample gigs.** `data/sample_gigs.json` ships four clearly labelled examples (a bakery
menu promotion, a tutoring one-page site, ten handloom product descriptions, and a plumbing price
list). Each uses the same field shape a published gig uses - business context, original request,
desired outcome, budget, deadline, objective, deliverables, required skills, acceptance criteria,
included work and exclusions, client responsibilities, revision expectations, clarifying questions,
assumptions/warnings, and the Gig Passport it derives - and each is scoped to a size a beginner
freelancer could realistically deliver for the stated example budget and deadline. The amounts are
illustrative and are **not** verified market rates.

**Safe refresh.** On startup, only records explicitly marked `sample` are refreshed to match the
shipped file. Real gigs are never modified, a file the user created themselves is left completely
untouched, sample ids are kept so applications linked to a sample still resolve, and the refresh is
idempotent (it does not rewrite the file when nothing changed). This means your own published gigs,
profiles, applications, assessment results, and interviews are preserved.

**One identity.** The tagline is the core promise - *Turn vague business requests into clear,
achievable freelance gigs* - and the same colours, headings, cards, chips, and status pills are used
across the homepage, business area, FairScope, the Gig Passport, and the student area.

**Clear layers in the business flow.** The editor keeps three things visibly separate: your
**original request** (shown exactly as written), the **AI draft + FairScope checks**, and the
**Gig Passport** you approve before publishing. The budget and deadline are never altered unless you
change them yourself.

**Student listing and proposal.** Gig cards show the business context, title, one-sentence outcome,
budget, deadline, essential skills, and whether the gig is published or a labelled **SAMPLE**. The
detail view shows the same published Gig Passport the business approved. The proposal step shows the
gig's objective, deliverables, and required skills, plus which of the required skills the profile
lists and which it does not (computed in Python, never invented), followed by an exact review of the
proposal before submission.

**Sample refresh is safe for runtime data.** Refreshing samples only rewrites records marked
`sample`; real gigs, profiles, applications, assessment results, and interview records are never
touched, and the refresh is idempotent. This is covered by tests that use temporary folders.

---

## The workspace shell

The interface is one dashboard-style workspace rather than a set of separate forms. The design
system lives entirely in `ui_common.py` as scoped CSS over Streamlit's own components, so there
are no new dependencies and nothing is a static mockup.

**The shell.** A pale lavender canvas holds one inset white shell: a 248 px lavender sidebar on the
left and a white content canvas with a compact header. The sidebar carries the Gigsie wordmark and
nine real destinations in three groups —

| Group | Destinations |
|---|---|
| Workspace | Overview |
| Business | Create with AI, Published Gigs, Applicants & Interviews |
| Student | Find Work, My Profile, My Applications, Skill Assessments, Interviews |

— plus an honest prototype footer pinned to the bottom. The active destination is highlighted, and
every one of them performs real navigation; there are no decorative links.

**One navigation system, and only one.** The sidebar is permanent: Streamlit's collapse control and
the auto-collapse that happens on narrow viewports are both disabled, so navigation can never
disappear. There is **no second navigation layer** anywhere — no horizontal tab bar in the student
area, no in-page section switch, and the header carries **no** navigation control at all: the old
*← Back to start* link and the Business/Student role switch were both removed because each
duplicated a destination the sidebar already shows on every page. Gig Passport and Student Overview
remain real routes, reached through the workflow rather than listed twice at the top level.

**The header.** Each page opens with a breadcrumb, a status chip that shows the real local student
profile (or the real count of locally published gigs), and one context-appropriate primary action.
On Published Gigs a search field filters the gigs actually saved on the device. The search is only
rendered where it filters real saved records, so it can never sit in front of a workflow form.

**No horizontal overflow.** Streamlit's columns default to `min-width: auto`, which lets one long
title stretch an entire row wider than the viewport. The columns are pinned to `min-width: 0` and
the text is allowed to wrap, and a `@media (max-width: 1024px)` fallback stacks columns into
single full-width rows instead of squeezing them. Body copy is capped at a readable measure and the
content card is capped at 1320 px, so a wide window does not stretch text into long unreadable
lines. This is verified in-browser on every page at both a laptop and a desktop width.

**Overview.** The home page is a dashboard: a welcome header with the value proposition, the two
real entry points (*Start a business request*, *Enter the student area*), four metric tiles
(published gigs, applications, interview requests, labelled samples), a three-column panel row
(Your Gigs, how a gig becomes clear, needs attention), a compact pending-applications panel shown
only when real applications exist, and a table of every saved gig. When nothing is saved it shows an
empty state instead of inventing activity.

**Business pages.** Each workflow has its own page, so no page is a single long column:

| Page | Contents |
|---|---|
| Gig Passport | The spacious editor (title, objective, deliverables, required skills, acceptance criteria, collapsible AI suggestions and checks, the full passport sections, acknowledgement checkboxes) and the explicit **Publish gig**. Empty state with a route back to Create when there is no draft. |
| Published Gigs | Metric tiles, search, and gig cards built from the saved records. Samples listed last and labelled. |
| Applicants & Interviews | Metric tiles plus the real applicant/interview management. |

A numbered step rail tracks progress: describe → generate → review FairScope → compare strategies →
edit the Gig Passport → publish.

**Student pages.** The overview shows the real profile name and self-reported skills, honest metric
tiles, ranked opportunities from the existing deterministic matcher, and only the real items waiting
for attention. Find Work renders marketplace-style gig cards with a real *View Gig* action, budget,
deadline, skill tags, and a real match line; the detail view shows the same published Gig Passport
the business approved. Practice assessments stay labelled practice, and interviews show only the
stored status.

**One source of truth.** `ui_common.gig_card()` and the `gig_*` helpers build every gig card from
the saved record, so the business dashboard, the published list, the student browse grid, the gig
from those same saved fields.

**Honest states preserved.** Loading indicators still appear only where the model is actually
called, the selected scope strategy still never overwrites the draft without an explicit choice,
publishing still reports success only after the record is saved, and storage failures still surface
as clear errors instead of false success. No revenue, user counts, ratings, applicant counts,
notifications, or avatars are invented.

---

## Stage 9 — one navigation system and a focused workspace

Stage 9.1 addressed the defects found by reviewing the real rendered app: the
sidebar could auto-collapse and leave a large blank panel, the header duplicated
navigation that the sidebar already provided, titles and step pills were oversized,
one long gig title stretched the whole page horizontally, and the strategy
comparison could display *Proposed: Unknown strategy*.

**Navigation.** The sidebar is now permanent (Streamlit's collapse control and
auto-collapse are disabled) and lists exactly nine destinations in the groups
Workspace / Business / Student. The header's *← Back to start* link and the
Business/Student role switch were **removed** — each duplicated a destination the
sidebar already shows — and `_role_switch` was deleted. The header is now
breadcrumb, real workspace context, and one primary action.

**Layout.** Titles, step pills, and spacing were reduced; the step rail is one
compact line; the content card is capped at 1320 px with body copy capped at a
readable measure; and a `@media (max-width: 1024px)` rule stacks columns instead
of squeezing them. Two conflicting media queries were removed, one of which made
the page title *larger* below 1100 px and another of which hid the workspace chip
below 1200 px.

**Strategy identity.** Fixed at the data-flow level rather than by relabelling:
see the note in the FairScope section above.

**Tests updated for the changed contract.** The assertions that encoded the old
header controls (back-to-start, role switch, the extra sidebar items) were
rewritten to assert the new behaviour — including a test that the header carries
*no* navigation control and that *Unknown strategy* can never appear. No assertion
was weakened or removed, and the workflows they covered are still checked.

---

## FairScope evaluation experiment

Gigsie's draft-then-review workflow is evaluated by a small reproducible harness
rather than asserted by hand:

```powershell
# structural self-check, no API calls
.\.venv\Scripts\python.exe scripts\evaluate_fairscope.py --self-check

# live run: 5 synthetic cases, 5 Groq calls, writes real results
.\.venv\Scripts\python.exe scripts\evaluate_fairscope.py --live --json docs\evaluation_results.json
```

The dataset is `data/evaluation_cases.json` (five synthetic scenarios, clearly
labelled as invented examples, not real jobs or verified market rates). The
rubric reuses the product's own `fairscope` and `validation` helpers, scores the
raw draft and the reviewed Gig Passport with the same measurements, and reports
**structural measurements only** - never a quality, fairness, or accuracy score.

Method, criteria, measured results, failure cases, and limitations:
[`docs/FAIRSCOPE_EVALUATION.md`](docs/FAIRSCOPE_EVALUATION.md).

---

## Safety

- Never commit `.env`. It is already ignored by `.gitignore`.
- `.env.example` contains placeholders only, so it is safe to commit.
- `GROQ_API_KEY` is read only inside `gigsie_ai.py` and is never printed, returned, or
  embedded in an error message.
- Inference runs on Groq's servers; no local models are downloaded.

---

## Demo runbook: the central flow

This is the path to record for the DEV submission. It runs entirely in the
browser and needs a `GROQ_API_KEY` in `.env`.

**Setup (once)**
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# .env contains:  GROQ_API_KEY=your_key_here
.\.venv\Scripts\python.exe -m streamlit run app.py
```

**1. Business writes a request** — `Create with AI` in the sidebar. Fill the
form (budget and deadline are required), then **Generate task brief**. One real
Groq call runs `openai/gpt-oss-20b`; a spinner shows while it works.

**2. FairScope review** appears on the same page and is the centre of the
product. Point at:
- the original request beside the AI draft, so the model is visibly a *proposal*;
- **Clarity check** - deterministic Python results, each labelled;
- **Scope signals** vs **AI suggestions**, kept clearly apart;
- **Recommended next action**.

**3. Compare scope strategies** - pick *Outcome-first* from the dropdown and
click **Generate this strategy version**. A second Groq call returns a
**Proposed: Outcome-first** panel with *What changed*. Emphasise that the
current draft is unchanged, and that **Discard proposed version** leaves it
untouched.

**4. Edit the Gig Passport** - click **Continue to the Gig Passport**. Show the
**Before you publish** panel (real readiness, computed from the passport), any
`Needs clarification` rows, and the acknowledgement checkboxes. Then **Publish
gig**.

**5. Student finds the gig** - `Find Work` in the sidebar. The gig appears as a
card with budget, deadline, skills and a real skill match. **Create a student
profile** first if none exists. Open **View Gig** to show the Gig Passport is
*the same approved scope* the business saved.

**6. Submit a proposal** - write in the proposal box, **Review proposal**, then
**Submit application**. Apply again on the same gig to show duplicate
prevention.

**7. Business reviews it** - `Applicants & Interviews`. The saved proposal text
is shown verbatim with the real status. **Shortlist**, then **Request an
interview** with a future date.

**8. Interview loop** - back in `Interviews` as the student: **Accept this time**
(or propose an alternative). As the business: **Confirm agreed time**. The
status moves to `Confirmed` and is visible to both sides.

**Optional, if time allows** - `Skill Assessments` (generate, answer, and show
the deterministic Python grade) and `My Applications`.

**What not to claim on camera**: no earnings, user counts, ratings, verified
market rates, real accounts, payments, or messaging. Gigsie is a single-device
local prototype; sample gigs are labelled `SAMPLE` and their figures are
illustrative assumptions.

---

## Hacktoberfest submission slots

- **Demo video / live link:** _to be added before submitting_
- **Track:** DEV Challenge, Week 2 - Side Hustle
- **Model:** `openai/gpt-oss-20b` served through Groq
