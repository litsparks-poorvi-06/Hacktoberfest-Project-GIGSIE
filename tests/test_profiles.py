"""Unit tests for profiles.py (student profile validation and storage).

These run without Streamlit and without any API call, using a temporary data
folder so your real ``data/`` files are never touched.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import profiles  # noqa: E402
import storage  # noqa: E402
import validation  # noqa: E402
from errors import WorkflowError  # noqa: E402


def _valid_values() -> dict:
    return {
        "display_name": "Asha Rao",
        "skills": "Canva\nCopywriting",
        "skill_levels": "Canva: Beginner",
        "experience_level": "Beginner",
        "bio": "Second-year student who enjoys design.",
        "portfolio_links": ["https://example.com/asha"],
        "weekly_hours": 10,
    }


class ProfileValidationTests(unittest.TestCase):
    def test_valid_profile_has_no_errors(self) -> None:
        findings = profiles.validate_profile_input(_valid_values())
        self.assertFalse(validation.has_errors(findings), findings)

    def test_missing_display_name_is_an_error(self) -> None:
        values = _valid_values()
        values["display_name"] = ""
        findings = profiles.validate_profile_input(values)
        self.assertTrue(validation.has_errors(findings))

    def test_missing_skills_is_an_error(self) -> None:
        values = _valid_values()
        values["skills"] = "   "
        findings = profiles.validate_profile_input(values)
        self.assertTrue(validation.has_errors(findings))

    def test_missing_weekly_hours_is_an_error(self) -> None:
        values = _valid_values()
        values["weekly_hours"] = 0
        findings = profiles.validate_profile_input(values)
        messages = " ".join(f["message"] for f in findings)
        self.assertIn("weekly availability", messages.lower())

    def test_bad_portfolio_link_is_only_a_warning(self) -> None:
        values = _valid_values()
        values["portfolio_links"] = ["not a web address"]
        findings = profiles.validate_profile_input(values)
        self.assertFalse(validation.has_errors(findings), findings)
        self.assertTrue(any(f["level"] == "warning" for f in findings))

    def test_skill_level_for_unknown_skill_warns(self) -> None:
        values = _valid_values()
        values["skill_levels"] = "Photoshop: Advanced"
        findings = profiles.validate_profile_input(values)
        self.assertTrue(
            any("not in your skills list" in f["message"] for f in findings), findings
        )

    def test_not_a_dict_is_an_error(self) -> None:
        findings = profiles.validate_profile_input("nope")
        self.assertTrue(validation.has_errors(findings))


class ProfileBuildTests(unittest.TestCase):
    def test_build_profile_parses_lists_and_levels(self) -> None:
        profile = profiles.build_profile(_valid_values())
        self.assertEqual(profile["skills"], ["Canva", "Copywriting"])
        self.assertEqual(profile["skill_levels"], {"Canva": "beginner"})
        self.assertEqual(profile["portfolio_links"], ["https://example.com/asha"])
        self.assertEqual(profile["weekly_hours"], 10.0)
        self.assertTrue(profile["id"].startswith("p_"))

    def test_availability_uses_hours_not_days(self) -> None:
        profile = profiles.build_profile(_valid_values())
        self.assertEqual(profile["available_time"], "10 hrs/week")
        # A weekly-hours figure must never be read as a number of days.
        self.assertIsNone(validation.parse_duration_days(profile["available_time"]))

    def test_missing_hours_leaves_availability_blank(self) -> None:
        values = _valid_values()
        values["weekly_hours"] = 0
        profile = profiles.build_profile(values)
        self.assertEqual(profile["available_time"], "")


class ProfileStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_save_creates_then_updates_the_same_profile(self) -> None:
        first = profiles.save_profile(_valid_values(), data_dir=self.data_dir)
        self.assertEqual(len(storage.load_profiles(self.data_dir)), 1)

        updated_values = _valid_values()
        updated_values["display_name"] = "Asha R."
        updated_values["skills"] = "Canva\nCopywriting\nPhotography"
        second = profiles.save_profile(
            updated_values, profile_id=first["id"], data_dir=self.data_dir
        )

        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["created_at"], first["created_at"])
        stored = storage.load_profiles(self.data_dir)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["display_name"], "Asha R.")
        self.assertIn("Photography", stored[0]["skills"])

    def test_save_as_new_creates_a_second_profile(self) -> None:
        profiles.save_profile(_valid_values(), data_dir=self.data_dir)
        profiles.save_profile(_valid_values(), data_dir=self.data_dir)
        self.assertEqual(len(storage.load_profiles(self.data_dir)), 2)

    def test_save_rejects_invalid_profile(self) -> None:
        values = _valid_values()
        values["display_name"] = ""
        with self.assertRaises(WorkflowError):
            profiles.save_profile(values, data_dir=self.data_dir)
        self.assertEqual(storage.load_profiles(self.data_dir), [])

    def test_load_and_list_profiles(self) -> None:
        saved = profiles.save_profile(_valid_values(), data_dir=self.data_dir)
        self.assertEqual(profiles.list_profiles(self.data_dir)[0]["id"], saved["id"])
        self.assertEqual(profiles.load_profile(saved["id"], self.data_dir)["id"], saved["id"])
        self.assertIsNone(profiles.load_profile("missing", self.data_dir))
        self.assertIsNone(profiles.load_profile(None, self.data_dir))

    def test_storage_failure_is_reported(self) -> None:
        # Point the data dir at a path that cannot be a directory.
        blocked = Path(self._tmp.name) / "blocked_file"
        blocked.write_text("not a directory", encoding="utf-8")
        with self.assertRaises(storage.StorageError):
            profiles.save_profile(_valid_values(), data_dir=blocked)


if __name__ == "__main__":
    unittest.main()
