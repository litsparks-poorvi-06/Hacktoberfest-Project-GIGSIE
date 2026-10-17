"""Gigsie Voice Brief - narration of the scope Gigsie actually produced.

This is the ElevenLabs part of Gigsie. It narrates the *real* content of a
generated brief and its Gig Passport so a business owner or a student can listen
to the same scope they can read. It is an accessibility and comprehension
feature, not a separate content pipeline: :func:`build_fairscope_narration` and
:func:`build_passport_narration` read only fields that FairScope and the
workflow already produced, and they never invent a figure.

Design constraints
------------------
* **No new dependency.** The synchronous ElevenLabs Text-to-Speech endpoint is a
  plain JSON POST, so this module uses the standard library only.
* **Never narrate on a rerun.** Synthesis happens only when the user explicitly
  asks for it; the caller owns the session-state cache and this module provides
  the cache key.
* **No secrets anywhere.** The key is read from the environment, sent in the
  ``xi-api-key`` header, and never returned, logged, or embedded in an error.
* **No fabrication.** If a value is missing, the narration says it is not
  specified instead of guessing.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from typing import Any

# The official synchronous endpoint. See
# https://elevenlabs.io/docs/api-reference/text-to-speech/convert
API_URL_TEMPLATE = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

DEFAULT_MODEL_ID = "eleven_multilingual_v2"

ENV_API_KEY = "ELEVENLABS_API_KEY"
ENV_VOICE_ID = "ELEVENLABS_VOICE_ID"
ENV_MODEL_ID = "ELEVENLABS_MODEL_ID"

# Narration is a summary, not an audiobook. A long brief is trimmed at a
# readable length rather than sent as an unbounded request.
MAX_CHARS = 4000
DEFAULT_TIMEOUT_SECONDS = 45.0

# How much of each list is spoken before moving on.
_MAX_SPOKEN_ITEMS = 5


class VoiceBriefError(RuntimeError):
    """Raised when narration could not be produced.

    The message is safe to show in the UI: it never contains the API key.
    """


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def is_configured() -> bool:
    """True when both the key and the voice are present in the environment."""
    return bool(voice_id() and api_key())


def api_key() -> str:
    return (os.environ.get(ENV_API_KEY) or "").strip()


def voice_id() -> str:
    return (os.environ.get(ENV_VOICE_ID) or "").strip()


def model_id() -> str:
    configured = (os.environ.get(ENV_MODEL_ID) or "").strip()
    return configured or DEFAULT_MODEL_ID


def configuration_note() -> str:
    """An unobtrusive setup hint that never reveals or asks for a real key."""
    missing = []
    if not api_key():
        missing.append(ENV_API_KEY)
    if not voice_id():
        missing.append(ENV_VOICE_ID)
    if not missing:
        return ""
    return (
        "Voice Brief is not configured yet. Set "
        + " and ".join(missing)
        + " in your local .env to enable it. Everything else in Gigsie works "
        "without it."
    )


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------
def narration_cache_key(text: str, voice: str | None = None, model: str | None = None) -> str:
    """A stable cache key for one narration request.

    Identical text with the same voice and model returns the same key, so an
    ordinary rerun reuses the audio instead of spending another request. Change
    the text, the voice, or the model and the key changes, so the cache
    invalidates on its own.
    """
    payload = "\x1f".join(
        [
            (text or "").strip(),
            (voice or "").strip(),
            (model or model_id()).strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------
def build_request(
    text: str,
    voice: str | None = None,
    model: str | None = None,
) -> urllib.request.Request:
    """Build the HTTP request. Exposed so tests can assert its shape."""
    voice_value = (voice or voice_id() or "").strip()
    if not voice_value:
        raise VoiceBriefError(
            f"No ElevenLabs voice is configured. Set {ENV_VOICE_ID} to enable Voice Brief."
        )
    if not (text or "").strip():
        raise VoiceBriefError("There is nothing to narrate yet.")

    body = json.dumps(
        {"text": _trim(text), "model_id": (model or model_id()).strip()}
    ).encode("utf-8")
    return urllib.request.Request(
        API_URL_TEMPLATE.format(voice_id=voice_value),
        data=body,
        headers={
            "xi-api-key": api_key(),
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )


def synthesize(
    text: str,
    voice: str | None = None,
    model: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> bytes:
    """Return the audio bytes for ``text``.

    Raises :class:`VoiceBriefError` with a message that is safe to show.
    """
    if not api_key():
        raise VoiceBriefError(
            f"Voice Brief is not configured. Set {ENV_API_KEY} to enable it."
        )

    request = build_request(text, voice=voice, model=model)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            audio = response.read()
    except urllib.error.HTTPError as error:
        # The response body can echo the key back; never surface it.
        raise VoiceBriefError(
            f"ElevenLabs rejected the narration request (HTTP {error.code})."
        ) from None
    except urllib.error.URLError as error:
        raise VoiceBriefError(
            "Could not reach ElevenLabs. Check the network and try again."
        ) from None
    except TimeoutError:
        raise VoiceBriefError(
            "The narration request timed out. Try again with a shorter summary."
        ) from None
    except OSError:
        raise VoiceBriefError(
            "Could not reach ElevenLabs. Check the network and try again."
        ) from None

    if not audio:
        raise VoiceBriefError("ElevenLabs returned no audio for this summary.")
    return audio


# ---------------------------------------------------------------------------
# Narration scripts built from the real generated scope
# ---------------------------------------------------------------------------
def _text(*values: Any) -> str:
    for value in values:
        candidate = str(value or "").strip()
        if candidate:
            return candidate
    return ""


def _spoken_list(label: str, values: Any, joiner: str = "and") -> str:
    items = _string_list(values)
    if not items:
        return f"{label} are not specified yet."
    if len(items) == 1:
        return f"{label}: {items[0]}."
    if len(items) == 2:
        return f"{label}: {items[0]} {joiner} {items[1]}."
    return f"{label}: {', '.join(items[:-1])}, {joiner} {items[-1]}."


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        lines = [line.strip(" -*\t") for line in value.splitlines()]
    elif isinstance(value, (list, tuple)):
        lines = [str(item).strip(" -*\t") for item in value]
    else:
        lines = []
    cleaned = [line for line in lines if line]
    return cleaned[:_MAX_SPOKEN_ITEMS]


def _budget_sentence(request: dict[str, Any]) -> str:
    budget = request.get("budget")
    try:
        budget_value = float(budget) if budget not in (None, "") else 0.0
    except (TypeError, ValueError):
        budget_value = 0.0

    deadline = _text(request.get("deadline"))
    parts: list[str] = []
    if budget_value > 0:
        parts.append(f"budget {budget_value:,.0f} rupees")
    if deadline:
        parts.append(f"deadline {deadline}")
    if not parts:
        return "No budget or deadline has been set yet."
    return "Stated " + " and ".join(parts) + ". These are not changed by Gigsie."


def _finding_messages(findings: Any, levels: tuple[str, ...]) -> list[str]:
    if not isinstance(findings, (list, tuple)):
        return []
    messages: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if finding.get("level") not in levels:
            continue
        message = str(finding.get("message") or "").strip()
        if message:
            messages.append(message)
        if len(messages) >= 3:
            break
    return messages


def build_fairscope_narration(
    brief: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
    analysis: dict[str, Any] | None = None,
) -> str:
    """Narrate the draft brief and its FairScope review.

    Every sentence comes from the draft, the request, or the review that is
    already on screen. Nothing is added.
    """
    brief = brief or {}
    request = request or {}
    analysis = analysis or {}

    title = _text(brief.get("title")) or "this task"
    business = _text(request.get("project_name"))
    opening = (
        f"Here is the scope Gigsie drafted for {business}."
        if business
        else "Here is the scope Gigsie drafted."
    )

    sentences = [opening, f"The draft is titled {title}."]

    objective = _text(brief.get("objective"))
    if objective:
        sentences.append(f"The business needs {objective}")
        sentences[-1] = sentences[-1] + (
            "." if objective.endswith((".", "!", "?")) else "."
        )
    else:
        sentences.append("No objective has been written yet.")

    sentences.append(_spoken_list("The deliverables", brief.get("deliverables")))
    sentences.append(_spoken_list("The required skills", brief.get("required_skills")))
    sentences.append(_budget_sentence(request))

    # Deterministic findings: what FairScope can actually see.
    checks = ((analysis.get("clarity") or {}).get("checks")) or []
    unresolved = [
        check
        for check in checks
        if isinstance(check, dict)
        and check.get("status") in {"needs_clarification", "missing"}
    ]
    if unresolved:
        labels = _string_list([check.get("label") for check in unresolved])
        sentences.append(f"FairScope still needs clarity on {', '.join(labels)}.")
    else:
        sentences.append("FairScope found no missing scope information.")

    signals = _finding_messages(analysis.get("signals"), ("error", "warning"))
    if signals:
        sentences.append(f"Scope risks: {'; '.join(signals)}")

    # The model's own notes, always labelled as the model's.
    ai_suggestions = analysis.get("ai_suggestions") or {}
    questions = _string_list(ai_suggestions.get("questions"))
    if questions:
        sentences.append(f"Open questions raised by the model: {'; '.join(questions)}")

    action = analysis.get("next_action") or {}
    summary = _text(action.get("summary"))
    if summary:
        sentences.append(f"Recommended next step: {summary}")

    sentences.append(
        "This is a draft for your review. Nothing is published until you approve it."
    )
    return _trim(" ".join(s for s in sentences if s))


def build_passport_narration(
    gig: dict[str, Any] | None = None,
    passport: dict[str, Any] | None = None,
) -> str:
    """Narrate the agreed Gig Passport that students will read."""
    gig = gig or {}
    passport = passport or {}
    sections = passport.get("sections") or {}

    title = _text(gig.get("title")) or "this gig"
    business = _text(gig.get("business_name"))
    opening = (
        f"{title}, published by {business}."
        if business
        else f"{title}."
    )

    sentences = [opening]

    objective = _section_value(sections, "objective") or _text(
        (gig.get("brief") or {}).get("objective") if isinstance(gig.get("brief"), dict) else ""
    )
    if objective:
        sentences.append(f"The objective is: {objective}")
    else:
        sentences.append("No objective has been written yet.")

    for key, label in (
        ("deliverables", "The deliverables"),
        ("definition_of_done", "Definition of done"),
        ("included_work", "Included work"),
        ("exclusions", "Exclusions"),
        ("required_skills", "Required skills"),
        ("client_responsibilities", "What the client provides"),
        ("revision_expectations", "Revision expectations"),
    ):
        value = _section_value(sections, key)
        if value:
            sentences.append(_spoken_list(label, value))

    budget = _text(gig.get("budget_inr"))
    deadline = _text(gig.get("deadline"))
    if budget:
        sentences.append(f"The budget is {budget} rupees.")
    else:
        sentences.append("No budget has been set.")
    sentences.append(f"The deadline is {deadline}." if deadline else "No deadline has been set.")

    for key, label in (
        ("open_questions", "Open questions"),
        ("scope_warnings", "Warnings"),
        ("assumptions", "Assumptions"),
    ):
        value = _section_value(sections, key)
        if value:
            sentences.append(_spoken_list(label, value))

    sentences.append(
        "This is the agreed scope. Anything not specified above was never confirmed."
    )
    return _trim(" ".join(s for s in sentences if s))


def _section_value(sections: dict[str, Any], key: str) -> str:
    section = sections.get(key)
    if not isinstance(section, dict):
        return ""
    if section.get("needs_clarification"):
        return ""
    value = section.get("value")
    if isinstance(value, (list, tuple)):
        items = _string_list(value)
        return "; ".join(items)
    return str(value or "").strip()


def _trim(text: str) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= MAX_CHARS:
        return cleaned
    # Cut on a sentence boundary where possible so the audio never stops mid-word.
    clipped = cleaned[:MAX_CHARS]
    boundary = max(clipped.rfind(". "), clipped.rfind("? "), clipped.rfind("! "))
    if boundary > MAX_CHARS // 2:
        return clipped[: boundary + 1]
    return clipped.rsplit(" ", 1)[0] + "."
