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

> **Current status (Phase 2).** The Streamlit interface, required-input validation, and the
> "Generate Task Brief" button are built and working. Budget and deadline are optional.
> The Groq AI integration in `gigsie_ai.py` is implemented and tested, but it is **not wired
> into the interface yet** - the results section currently shows placeholders. The next phase
> connects the two.

---

## How it works (and why it is split in two)

Gigsie separates the model's job from Python's job on purpose:

| Layer | File | Responsibility |
|---|---|---|
| AI (hosted on Groq) | `gigsie_ai.py` | Understands the request and drafts the brief as JSON. |
| Deterministic checks | `validation.py` | Plain Python rules: missing info, deadline vs. scope, etc. |
| Interface & flow | `app.py` | Streamlit form, review, edit, download. |

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
├── app.py             # Streamlit interface and application flow
├── gigsie_ai.py        # Groq integration, prompt, JSON parsing
├── validation.py       # Deterministic validation checks (no AI, no network)
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

**What to expect (Phase 2):**
1. Fill in the form. Only **What work needs to be done?** and **What outcome does the business
   want?** are required; name, budget, deadline, and additional information are optional.
2. If a required field is missing, Gigsie shows a helpful error and stops.
3. Click **Generate Task Brief** to validate the request.
4. The result section confirms the captured request and shows a placeholder with the headings
   of the brief (objective, deliverables, skills, questions, acceptance criteria, assumptions,
   scope warnings). No AI is called yet.
   (The next phase replaces these placeholders with the AI-generated brief, scope checks,
   editing, and Markdown download.)

---

## Testing

Everything below uses synthetic requests only.

```powershell
# 1. Compile check
python -m py_compile app.py gigsie_ai.py validation.py testgroq.py

# 2. Offline logic tests (parsing + validation, no API call)
#    Covered by ad-hoc checks: valid JSON, fenced JSON, prose-wrapped JSON,
#    malformed JSON, empty response, missing fields.

# 3. End-to-end (requires the API)
python testgroq.py
streamlit run app.py
```

Verified behaviours:
- Valid JSON, JSON in code fences, and JSON surrounded by extra text all parse correctly.
- Malformed and empty responses raise a clean, user-friendly error instead of crashing.
- Missing fields in the model output are reported, not silently dropped.
- Deterministic checks flag missing info and "many deliverables in a short deadline".
- A live Groq request generates and parses a brief successfully.

If the API is unavailable or the key is missing, Gigsie reports the actual error message
rather than pretending to succeed.

---

## Limitations and honest notes

- AI output can vary between runs. Gigsie prefers Groq's JSON mode, but the model can still
  occasionally return something unexpected; the app handles that gracefully and asks you to try again.
- The deterministic checks are simple heuristics (documented in `validation.py`). They prompt a
  human to think — they are not rules about productivity or price.
- Gigsie does not verify facts, estimate market rates, or guarantee any outcome.
- This is a review tool, not a marketplace: no accounts, payments, or hiring.

---

## Safety

- Never commit `.env`. It is already ignored by `.gitignore`.
- The API key is read only inside `gigsie_ai.py` and is never printed or returned.
- Inference runs on Groq's servers; no local models are downloaded.
