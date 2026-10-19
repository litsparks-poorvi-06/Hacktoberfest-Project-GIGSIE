# FairScope Evaluation Experiment

An evaluation of whether Gigsie's existing **GPT-OSS draft → FairScope review →
Gig Passport** workflow produces structured, internally consistent freelance
task briefs, and whether FairScope's deterministic checks correctly detect
requests that are genuinely underspecified.

This is an addition to the product, not a change to it. No UI, workflow, or
business logic was modified for this experiment.

---

## 1. Research question

> When a small business writes a short, often vague request, does Gigsie's
> draft-then-review workflow produce a **structurally complete** brief, and do
> FairScope's deterministic checks **correctly detect** the cases that are
> genuinely underspecified — without firing on briefs that are fine?

Two separate claims, deliberately not merged:

1. **Completeness/consistency** — does the pipeline emit all required fields,
   and does it preserve the budget and deadline the business stated?
2. **Detection** — does FairScope catch the cases it should, and stay quiet on
   the ones it should not? This needs a negative control or it is meaningless.

---

## 2. Dataset

`data/evaluation_cases.json` — five synthetic cases. They are invented
evaluation examples, **not real customers, not real jobs, and not verified
market rates**. Amounts are illustrative assumptions chosen to be plausible for
a beginner freelancer.

| id | scenario | budget | deadline | declared expectation |
|---|---|---|---|---|
| `eval_bakery_social` | bakery social-media content | ₹800 | 2 days | no gap expected |
| `eval_tutor_landing` | tutor landing page | ₹2500 | 1 week | no gap expected |
| `eval_shop_descriptions` | shop product descriptions | ₹1200 | 3 days | gap expected |
| `eval_spreadsheet_cleanup` | spreadsheet cleanup | ₹1500 | 4 days | no gap expected |
| `eval_vague_marketing` | deliberately vague / over-scoped | ₹2000 | *(none)* | **gap must be detected** |

Each case declares `expect_detection` and a written `expect_reason` **before**
any model runs, so the criterion is not chosen after seeing the output.

The last case is the positive control: "help with marketing, do whatever is
needed", no deadline, no deliverables. A deterministic checker that cannot
flag that is not doing its job.

---

## 3. Method

```
request ──► gigsie_ai.generate_task_brief()   (one real Groq call, GPT-OSS)
                 │
                 ├─► artefact "draft"     : the brief exactly as returned
                 │
                 └─► fairscope.analyze_brief() + fairscope.build_passport()
                        │
                        └─► artefact "reviewed" : the Gig Passport the student reads
```

Both artefacts are scored by **the same rubric functions**
(`score_draft` / `score_reviewed` share every measurement). They are reported
separately and never merged, because they are different representations of the
same scope: FairScope does not silently rewrite the brief.

The implementation **reuses** `fairscope.clarity_checks`, `fairscope._is_specific`,
`fairscope._is_checkable`, `fairscope.build_passport`, `fairscope.passport_unresolved`,
`validation.validate_brief`, and `validation.extract_days`. No rule was
duplicated or re-implemented.

One model call per case, five calls total.

---

## 4. Criteria

### Structural measurements (automated)

| metric | how it is measured |
|---|---|
| `all_required_fields_present` | every required brief field is non-empty |
| `budget_preserved` | no finding claims the budget was changed, and no *different* INR figure appears in the brief |
| `deadline_preserved` | no finding claims the deadline was moved, and the brief states no conflicting duration |
| `deliverables_specific` | deliverables passing `fairscope._is_specific` |
| `criteria_checkable` | acceptance criteria passing `fairscope._is_checkable` |
| `unresolved_sections` | passport sections still flagged `Needs clarification` |

**Preservation is defined as "not contradicted", not "echoed".** The original
request is the source of truth and Gigsie never overwrites it, so a brief that
simply does not mention the deadline has not lost it.

### The detection criterion (right/wrong, pre-declared)

- A **gap** is counted only when a required field is genuinely absent: a
  `missing` clarity check, an **error**-level validation finding, or an
  unresolved passport section.
- **Advisories** — `needs_clarification` checks and warning-level signals — are
  recorded in `advisories_not_scored` and **never** counted as a hit or a miss.
  Real briefs draw advisories almost every time, so scoring them would make the
  measurement meaningless.
- `expect_detection: true` requires a gap (true positive).
- `expect_detection: false` requires no gap (true negative).

A warning is never counted as correct merely because it appeared.

### What is *not* claimed

No numeric quality, fairness, or accuracy score is produced, because none of
these can be established automatically:

- whether a brief is commercially sensible is a **human judgement**;
- whether a price is fair is **never** computed by Gigsie;
- whether an objective is well written **cannot** be decided by a regex;
- five cases is a demonstration, **not** a statistically meaningful sample.

---

## 5. Results

**These are real results from a real run** of `openai/gpt-oss-20b` through Groq
on 2026-10-19. Raw model output for every case is recorded in
`docs/evaluation_results.json` under `raw_brief`, so the rubric can be
re-applied without spending any further credit.

| metric | draft | reviewed |
|---|---|---|
| all required fields present | **100 %** | **100 %** |
| budget preserved | **100 %** | **100 %** |
| deadline preserved | **100 %** | **100 %** |

Detection:

| outcome | count |
|---|---|
| detection correct | **4 / 5** |
| true positives (gap found when required) | 1 |
| true negatives (no false alarm) | 3 |
| false negatives | 1 |

Per case:

| case | draft fields | reviewed fields | gap expected | gap found | result |
|---|---|---|---|---|---|
| `eval_bakery_social` | yes | yes | no | no | true negative |
| `eval_tutor_landing` | yes | yes | no | no | true negative |
| `eval_shop_descriptions` | yes | yes | **yes** | no | **false negative** |
| `eval_spreadsheet_cleanup` | yes | yes | no | no | true negative |
| `eval_vague_marketing` | yes | yes | **yes** | **yes** | true positive |

The vague, over-scoped request produced one unresolved passport section and was
correctly held back from a clean publish.

---

## 6. Failure cases and limitations

**The false negative (`eval_shop_descriptions`).** GPT-OSS produced a complete,
specific brief from a request whose *real* difficulty is that some spreadsheet
rows would be empty. FairScope analyses the brief and the request, not the
customer's actual spreadsheet, so it had nothing to detect. This is an honest
limit of the approach: **FairScope can only see what the request and the draft
contain.** A declared expectation of "gap always" was too strong for that case,
and the result stands as measured rather than being re-labelled afterwards.

**Other limitations, stated plainly:**

- **n = 5.** This is a demonstration of the method, not a benchmark. No
  confidence interval is claimed.
- **Single run, no repeats.** Model output varies between runs; no variance was
  measured.
- **Structural ≠ correct.** 100 % field completeness says nothing about whether
  the deliverables are the *right* ones. That is a human review step.
- **Detection criterion is deliberately strict.** Counting `needs_clarification`
  as a gap would raise the apparent detection rate but would also flag most
  healthy briefs, which is why it is excluded.
- **Advisory warnings were not scored.** They are reported separately and are
  the part most in need of human judgement.
- **Human judgements are still missing.** Nobody has rated whether these five
  briefs are actually *good* briefs. That is the main gap in this experiment.

---

## 7. Reproduction

Structural self-check — **no API calls, safe in CI**:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_fairscope.py --self-check
```

Live evaluation — 5 cases, 5 paid Groq calls, needs `GROQ_API_KEY` in `.env`:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_fairscope.py --live --json docs\evaluation_results.json
```

Re-score from the recorded model output — **no API calls**:

```python
import json, pathlib, sys
sys.path.insert(0, "scripts")
import evaluate_fairscope as h

data = json.loads(pathlib.Path("docs/evaluation_results.json").read_text())
cases = {c["id"]: c for c in h.load_cases()}
rows = []
for row in data["results"]:
    r = h.evaluate_case(cases[row["id"]], row["raw_brief"])
    r["live"] = True
    rows.append(r)
h.print_report(rows, h.summarise(rows))
```

The test suite never makes a paid call: `tests/test_fairscope_evaluation.py`
mocks the model boundary and asserts that no API call is made on import or in
self-check mode.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
