"""Local student profiles for Gigsie.

Honest scope (this is a prototype, not a product with accounts):

  * A profile is stored locally as JSON on this device. There is **no** real
    user account, no password, and no authentication.
  * ``profile_id`` exists only so applications, assessments, and interviews can
    be linked to the profile that created them inside this local storage.
  * Skills are **self-reported** - Gigsie never verifies them.

Deterministic checks live here and in ``validation.py``; the AI is never asked
to validate a profile.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from errors import WorkflowError
import storage
import validation

# Allowed per-skill / overall experience levels (matched after normalisation).
SKILL_LEVELS: tuple[str, ...] = ("beginner", "intermediate", "advanced")

# Display forms used in the UI.
SKILL_LEVEL_CHOICES: tuple[str, ...] = ("Beginner", "Intermediate", "Advanced")


def _now() -> str:
    return storage.now_iso()


def _text_list(value: Any) -> list[str]:
    """Coerce a newline-separated string or a list into a clean list."""
    if isinstance(value, str):
        return _split_lines(value)
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _to_hours(value: Any) -> float | None:
    """Return the weekly hours as a positive number, or None when unusable."""
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return None
    return hours if hours > 0 else None


def parse_skill_levels(text: Any, skills: list[str]) -> dict[str, str]:
    """Parse ``Skill: Level`` lines into {skill: level}.

    Only lines that name a skill already in ``skills`` are kept; anything else
    is ignored by the caller's validation, which reports it as a warning.
    """
    levels: dict[str, str] = {}
    if not isinstance(text, str):
        return levels
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, level = line.split(":", 1)
        name = name.strip()
        level = level.strip().lower()
        if name and level:
            levels[name] = level
    return levels


def format_availability(hours: Any) -> str:
    """Render weekly hours as free text for the availability comparison."""
    value = _to_hours(hours)
    if value is None:
        return ""
    number = int(value) if float(value).is_integer() else value
    return f"{number} hrs/week"


def build_profile(values: Any, profile_id: str | None = None) -> dict[str, Any]:
    """Turn raw form values (or an existing profile) into a stored profile.

    Tolerant by design: missing or oddly typed fields become safe defaults so
    ``validate_profile_input`` can report them as findings instead of crashing.
    """
    values = values if isinstance(values, dict) else {}

    skills = _text_list(values.get("skills"))

    raw_levels = values.get("skill_levels")
    if isinstance(raw_levels, dict):
        skill_levels = {
            str(name).strip(): str(level).strip().lower()
            for name, level in raw_levels.items()
            if str(name).strip()
        }
    else:
        skill_levels = parse_skill_levels(raw_levels, skills)

    links = _text_list(values.get("portfolio_links")) or _text_list(values.get("portfolio_url"))

    hours = _to_hours(values.get("weekly_hours"))

    display_name = str(values.get("display_name") or values.get("name") or "").strip()
    experience = str(values.get("experience_level") or "").strip()
    if not experience:
        experience = "Beginner"

    return {
        "id": profile_id or str(values.get("id") or "") or f"p_{uuid4().hex[:8]}",
        "display_name": display_name,
        "skills": skills,
        "skill_levels": skill_levels,
        "experience_level": experience,
        "bio": str(values.get("bio") or "").strip(),
        "portfolio_links": links,
        "weekly_hours": hours,
        # Free text used by validation.match_gig_to_skills' availability note.
        # Deliberately hour-based wording ("10 hrs/week") so no day count is
        # invented: an hours-per-week figure is not a number of days.
        "available_time": format_availability(hours),
        "created_at": str(values.get("created_at") or "") or _now(),
        "updated_at": _now(),
        # No authentication exists; make that explicit in the stored data.
        "identity_model": "local_prototype_profile",
    }


def validate_profile_input(values: Any) -> list[dict[str, str]]:
    """Validate raw profile form values. Returns findings (errors block saving)."""
    if not isinstance(values, dict):
        return [{"level": "error", "message": "The profile could not be read."}]

    profile = build_profile(values)
    findings: list[dict[str, str]] = list(validation.validate_profile(profile))

    if profile["weekly_hours"] is None:
        findings.append(
            {
                "level": "error",
                "message": "Add your weekly availability in hours (for example 10).",
            }
        )

    # Per-skill levels are optional, but should be usable if supplied.
    known = {validation.normalize_skill(skill) for skill in profile["skills"]}
    for skill, level in profile["skill_levels"].items():
        if validation.normalize_skill(level) not in SKILL_LEVELS:
            findings.append(
                {
                    "level": "warning",
                    "message": (
                        f"The level for '{skill}' should be Beginner, Intermediate, or "
                        "Advanced."
                    ),
                }
            )
        if validation.normalize_skill(skill) not in known:
            findings.append(
                {
                    "level": "warning",
                    "message": f"You set a level for '{skill}', but it is not in your skills list.",
                }
            )

    return findings


def save_profile(
    values: Any,
    profile_id: str | None = None,
    data_dir: Any = None,
) -> dict[str, Any]:
    """Validate and save a profile, creating it or updating it by ``profile_id``.

    Returns the stored profile. Raises ``WorkflowError`` when validation fails.
    """
    profile = build_profile(values, profile_id=profile_id)

    findings = validate_profile_input(profile)
    if validation.has_errors(findings):
        messages = [f["message"] for f in findings if f["level"] == "error"]
        raise WorkflowError("The profile cannot be saved yet: " + " ".join(messages))

    profiles = storage.load_profiles(data_dir)
    stored: dict[str, Any] | None = None
    for index, existing in enumerate(profiles):
        if existing.get("id") == profile["id"]:
            profile["created_at"] = existing.get("created_at") or profile["created_at"]
            profile["updated_at"] = _now()
            profiles[index] = profile
            stored = profile
            break
    if stored is None:
        profiles.append(profile)
        stored = profile

    storage.save_profiles(profiles, data_dir)
    return stored


def list_profiles(data_dir: Any = None) -> list[dict[str, Any]]:
    """Return every locally saved profile, oldest first."""
    return storage.load_profiles(data_dir)


def load_profile(profile_id: str | None, data_dir: Any = None) -> dict[str, Any] | None:
    """Return the profile with this id, or None."""
    if not profile_id:
        return None
    for profile in storage.load_profiles(data_dir):
        if profile.get("id") == profile_id:
            return profile
    return None
