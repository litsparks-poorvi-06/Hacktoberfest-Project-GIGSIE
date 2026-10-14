"""Local JSON persistence for Gigsie.

This module is the only place that reads and writes saved data. Keeping it
separate means the rest of the app never touches files directly, and tests can
run against a temporary folder instead of the real ``data/`` directory.

Design choices:
    * A missing file is NOT an error - it simply means "no data yet".
    * A corrupt or unreadable file raises ``StorageError`` so the UI can show a
      friendly message instead of crashing.
    * Writes go to a temporary file first, then replace the original, so a
      half-written file can never be left behind.

No API keys, secrets, or personal data are handled here.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The real data folder lives next to this file.
DATA_DIR = Path(__file__).resolve().parent / "data"
SAMPLES_FILE = DATA_DIR / "sample_gigs.json"


class StorageError(Exception):
    """Raised when saved data cannot be read or written safely.

    The message is safe to show to a user - it never contains secrets.
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    """Return the current UTC time as text, e.g. 2026-10-15T09:00:00+00:00."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _gigs_path(data_dir: Path | None) -> Path:
    return (data_dir or DATA_DIR) / "gigs.json"


def _applications_path(data_dir: Path | None) -> Path:
    return (data_dir or DATA_DIR) / "applications.json"


def _samples_path(data_dir: Path | None) -> Path:
    """Prefer a sample file inside the given folder, else the packaged one."""
    local = (data_dir or DATA_DIR) / "sample_gigs.json"
    return local if local.exists() else SAMPLES_FILE


def _read_json(path: Path) -> Any:
    """Read JSON from ``path``. Return None when the file does not exist.

    Raises StorageError when the file exists but cannot be read or parsed.
    """
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as error:
        raise StorageError(
            f"The file '{path.name}' is not valid JSON and could not be read."
        ) from error
    except OSError as error:
        raise StorageError(f"The file '{path.name}' could not be opened.") from error


def _write_json(path: Path, data: Any) -> None:
    """Write JSON safely: write to a temp file, then replace the target."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        os.replace(temp_path, path)
    except OSError as error:
        raise StorageError(f"The file '{path.name}' could not be saved.") from error


def _expect_list(data: Any, path: Path) -> list[dict]:
    if not isinstance(data, list):
        raise StorageError(f"The file '{path.name}' should contain a list of items.")
    return data


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Gigs
# ---------------------------------------------------------------------------
def load_gigs(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Return all saved gigs. A missing file means an empty list."""
    path = _gigs_path(data_dir)
    data = _read_json(path)
    if data is None:
        return []
    return _expect_list(data, path)


def save_gigs(gigs: list[dict[str, Any]], data_dir: Path | None = None) -> None:
    """Overwrite the gigs file with ``gigs``."""
    if not isinstance(gigs, list):
        raise StorageError("Gigs must be provided as a list.")
    _write_json(_gigs_path(data_dir), gigs)


def add_gig(gig: dict[str, Any], data_dir: Path | None = None) -> dict[str, Any]:
    """Add one gig, giving it an id/status/timestamp if it lacks them.

    Returns the stored record (with its new id).
    """
    gigs = load_gigs(data_dir)
    record = dict(gig)
    record.setdefault("id", _new_id("g"))
    record.setdefault("status", "open")
    record.setdefault("created_at", _now())
    record.setdefault("sample", False)
    gigs.append(record)
    save_gigs(gigs, data_dir)
    return record


def get_gig(gig_id: str, data_dir: Path | None = None) -> dict[str, Any] | None:
    """Return the gig with this id, or None if it is not found."""
    for gig in load_gigs(data_dir):
        if gig.get("id") == gig_id:
            return gig
    return None


def seed_samples_on_first_run(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Create ``gigs.json`` from the sample file the first time the app runs.

    If a gigs file already exists, it is left untouched. Returns the current gigs.
    """
    path = _gigs_path(data_dir)
    if path.exists():
        return load_gigs(data_dir)

    samples = _read_json(_samples_path(data_dir))
    if samples is None:
        samples = []
    samples = _expect_list(samples, _samples_path(data_dir))

    seeded: list[dict[str, Any]] = []
    for item in samples:
        record = dict(item)
        record["sample"] = True
        record.setdefault("status", "open")
        record.setdefault("id", _new_id("g"))
        record.setdefault("created_at", _now())
        seeded.append(record)

    _write_json(path, seeded)
    return seeded


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
def load_applications(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Return all saved application drafts. A missing file means an empty list."""
    path = _applications_path(data_dir)
    data = _read_json(path)
    if data is None:
        return []
    return _expect_list(data, path)


def save_application(
    application: dict[str, Any], data_dir: Path | None = None
) -> dict[str, Any]:
    """Add one application draft and return the stored record."""
    applications = load_applications(data_dir)
    record = dict(application)
    record.setdefault("id", _new_id("a"))
    record.setdefault("status", "draft")
    record.setdefault("created_at", _now())
    applications.append(record)
    _write_json(_applications_path(data_dir), applications)
    return record
