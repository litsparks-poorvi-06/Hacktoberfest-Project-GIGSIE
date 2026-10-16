"""Tests for storage.py - local JSON persistence.

Run from the project root with:
    python -m unittest discover -s tests -v

Every test uses a temporary folder, so your real data/ files are never touched.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Make sure the project root is importable when tests are run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import storage  # noqa: E402


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # --- reading -----------------------------------------------------------
    def test_missing_gigs_file_returns_empty_list(self) -> None:
        self.assertEqual(storage.load_gigs(self.data_dir), [])

    def test_missing_applications_file_returns_empty_list(self) -> None:
        self.assertEqual(storage.load_applications(self.data_dir), [])

    def test_corrupt_json_raises_storage_error(self) -> None:
        (self.data_dir / "gigs.json").write_text("{not valid json", encoding="utf-8")
        with self.assertRaises(storage.StorageError):
            storage.load_gigs(self.data_dir)

    def test_non_list_content_raises_storage_error(self) -> None:
        (self.data_dir / "gigs.json").write_text('{"a": 1}', encoding="utf-8")
        with self.assertRaises(storage.StorageError):
            storage.load_gigs(self.data_dir)

    # --- gigs --------------------------------------------------------------
    def test_save_and_load_roundtrip(self) -> None:
        gigs = [{"id": "g_1", "title": "Test gig", "sample": False}]
        storage.save_gigs(gigs, self.data_dir)
        self.assertEqual(storage.load_gigs(self.data_dir), gigs)

    def test_add_gig_sets_defaults(self) -> None:
        record = storage.add_gig({"title": "New gig"}, self.data_dir)
        self.assertTrue(record["id"].startswith("g_"))
        self.assertEqual(record["status"], "open")
        self.assertFalse(record["sample"])
        self.assertTrue(record["created_at"])
        # And it is actually persisted.
        self.assertEqual(len(storage.load_gigs(self.data_dir)), 1)

    def test_get_gig_finds_and_misses(self) -> None:
        record = storage.add_gig({"title": "Findable"}, self.data_dir)
        self.assertEqual(storage.get_gig(record["id"], self.data_dir)["title"], "Findable")
        self.assertIsNone(storage.get_gig("does_not_exist", self.data_dir))

    def test_add_gig_keeps_existing_id(self) -> None:
        record = storage.add_gig({"id": "g_fixed", "title": "Keep id"}, self.data_dir)
        self.assertEqual(record["id"], "g_fixed")

    # --- samples -----------------------------------------------------------
    def test_seed_creates_labelled_samples(self) -> None:
        seeded = storage.seed_samples_on_first_run(self.data_dir)
        self.assertGreater(len(seeded), 0)
        self.assertTrue(all(gig["sample"] is True for gig in seeded))
        # A second call must not duplicate or overwrite.
        again = storage.seed_samples_on_first_run(self.data_dir)
        self.assertEqual(len(seeded), len(again))

    def test_seed_does_not_overwrite_existing_data(self) -> None:
        storage.save_gigs([{"id": "g_mine", "title": "Mine"}], self.data_dir)
        result = storage.seed_samples_on_first_run(self.data_dir)
        self.assertEqual(result, [{"id": "g_mine", "title": "Mine"}])

    # --- applications ------------------------------------------------------
    def test_application_roundtrip(self) -> None:
        record = storage.save_application(
            {"gig_id": "g_1", "student_name": "Alex", "draft": {"opening": "Hi"}},
            self.data_dir,
        )
        self.assertTrue(record["id"].startswith("a_"))
        self.assertEqual(record["status"], "draft")
        loaded = storage.load_applications(self.data_dir)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["student_name"], "Alex")

    def test_saved_file_is_valid_json(self) -> None:
        storage.add_gig({"title": "Check file"}, self.data_dir)
        written = json.loads((self.data_dir / "gigs.json").read_text(encoding="utf-8"))
        self.assertIsInstance(written, list)

    # --- write robustness (transient Windows file locks) -------------------
    def test_write_survives_a_transient_replace_permission_error(self) -> None:
        # Windows can briefly refuse os.replace while something holds the target
        # open; a single transient error must not lose the save.
        real_replace = storage.os.replace
        calls = {"count": 0}

        def flaky_replace(src, dst):
            calls["count"] += 1
            if calls["count"] == 1:
                raise PermissionError(5, "Access is denied")
            return real_replace(src, dst)

        with mock.patch.object(storage.os, "replace", side_effect=flaky_replace):
            storage.save_gigs([{"id": "g_1", "title": "Saved"}], self.data_dir)

        self.assertEqual(storage.load_gigs(self.data_dir), [{"id": "g_1", "title": "Saved"}])
        self.assertGreaterEqual(calls["count"], 2)

    def test_write_gives_up_after_persistent_permission_errors(self) -> None:
        with mock.patch.object(
            storage.os, "replace", side_effect=PermissionError(5, "Access is denied")
        ):
            with self.assertRaises(storage.StorageError):
                storage.save_gigs([{"id": "g_1"}], self.data_dir)
        # A failed save never leaves a half-written target behind.
        self.assertFalse((self.data_dir / "gigs.json").exists())

    def test_no_temporary_file_is_left_behind(self) -> None:
        storage.save_gigs([{"id": "g_1"}], self.data_dir)
        self.assertEqual(list(self.data_dir.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
