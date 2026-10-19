"""Tests for the labelled sample gigs and the sample-refresh behaviour.

Three things are checked here, all with temporary folders so your real ``data/``
files are never touched:

  * the shipped sample file is internally consistent (every sample has the same
    fields, and its derived Gig Passport has no unresolved essentials),
  * refreshing samples is safe: only records marked ``sample`` change, real gigs
    and linked applications are preserved, and repeated refreshes are idempotent,
  * a published gig's approved passport is exactly what the student view reads.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import applications  # noqa: E402
import fairscope  # noqa: E402
import gig_workflow  # noqa: E402
import storage  # noqa: E402
import validation  # noqa: E402

SAMPLES_FILE = Path(__file__).resolve().parents[1] / "data" / "sample_gigs.json"


def _load_samples() -> list[dict]:
    with SAMPLES_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class SampleFileSchemaTests(unittest.TestCase):
    """The shipped sample file must be complete and internally consistent."""

    def test_has_several_labelled_samples(self) -> None:
        samples = _load_samples()
        self.assertGreaterEqual(len(samples), 4)
        for sample in samples:
            self.assertTrue(sample.get("sample"), sample.get("id"))

    def test_every_sample_has_the_shared_fields(self) -> None:
        for sample in _load_samples():
            for field in (
                "id",
                "title",
                "business_name",
                "work_needed",
                "desired_outcome",
                "budget_inr",
                "deadline",
                "required_skills",
                "brief",
                "status",
                "created_at",
            ):
                self.assertIn(field, sample, f"{sample.get('id')} missing {field}")
            self.assertGreater(float(sample["budget_inr"]), 0)
            self.assertTrue(str(sample["deadline"]).strip())
            self.assertTrue(sample["required_skills"])
            self.assertTrue(str(sample["work_needed"]).strip())
            self.assertTrue(str(sample["desired_outcome"]).strip())

    def test_brief_fields_are_complete_and_use_one_schema(self) -> None:
        for sample in _load_samples():
            brief = sample["brief"]
            for field in (
                "objective",
                "deliverables",
                "required_skills",
                "clarifying_questions",
                "acceptance_criteria",
                "assumptions",
                "exclusions",
                "client_responsibilities",
                "revision_expectations",
            ):
                self.assertIn(field, brief, f"{sample.get('id')} brief missing {field}")
                self.assertTrue(brief[field], f"{sample.get('id')} has empty {field}")
            # The current schema is used throughout - no leftover legacy keys.
            self.assertNotIn("project_objective", brief)
            self.assertNotIn("proposed_deliverables", brief)
            # A short deadline should not carry an unreasonable list of items.
            self.assertLessEqual(len(sample["brief"]["deliverables"]), 3)

    def test_sample_ids_are_unique(self) -> None:
        ids = [sample["id"] for sample in _load_samples()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_sample_derives_a_complete_passport(self) -> None:
        for sample in _load_samples():
            passport = fairscope.passport_for_gig(sample)
            self.assertEqual(
                fairscope.passport_essential_issues(passport),
                [],
                f"{sample.get('id')} has an unresolved essential passport section",
            )
            # The derived passport must agree with the brief it came from.
            self.assertEqual(
                passport["sections"]["objective"]["value"],
                sample["brief"]["objective"],
            )
            self.assertEqual(
                passport["sections"]["deliverables"]["value"],
                sample["brief"]["deliverables"],
            )
            self.assertEqual(
                passport["sections"]["required_skills"]["value"],
                sample["brief"]["required_skills"],
            )

    def test_samples_expose_matching_skills(self) -> None:
        for sample in _load_samples():
            self.assertTrue(validation.get_required_skills(sample))
            self.assertTrue(validation.get_deliverables(sample))


class SampleCoverageTests(unittest.TestCase):
    """The four release scenarios, and the honesty rules that apply to all of them."""

    #: The scenarios the release must ship, keyed by a word that identifies each.
    EXPECTED_SCENARIOS = {
        "bakery": ("bakery", 800.0, "2 days"),
        "tutor": ("tutoring", 2500.0, "1 week"),
        "product_descriptions": ("handloom", 1200.0, "3 days"),
        "presentation": ("slide deck", 1500.0, "4 days"),
    }

    def _find(self, needle: str) -> dict:
        for sample in _load_samples():
            haystack = " ".join(
                [
                    str(sample.get("title", "")),
                    str(sample.get("business_name", "")),
                    str(sample.get("work_needed", "")),
                ]
            ).lower()
            if needle in haystack:
                return sample
        self.fail(f"no sample gig mentions {needle!r}")

    def test_each_required_scenario_is_present_with_its_figures(self) -> None:
        for label, (needle, budget, deadline) in self.EXPECTED_SCENARIOS.items():
            with self.subTest(scenario=label):
                sample = self._find(needle)
                self.assertEqual(float(sample["budget_inr"]), budget)
                self.assertEqual(sample["deadline"], deadline)

    def test_the_presentation_sample_uses_owner_supplied_information(self) -> None:
        brief = self._find("slide deck")["brief"]
        text = " ".join(
            [str(brief.get("objective", ""))]
            + list(brief.get("assumptions") or [])
            + list(brief.get("client_responsibilities") or [])
        ).lower()
        self.assertIn("owner", text)
        self.assertIn("suppl", text)

    def test_no_sample_promises_work_outside_its_scope(self) -> None:
        forbidden = [
            "guarantee",
            "rank first",
            "first page of google",
            "increase sales",
            "boost sales",
            "unlimited revisions",
            "full marketing campaign",
            "professional photography",
        ]
        for sample in _load_samples():
            haystack = " ".join(
                [str(sample.get("title", ""))]
                + list(sample["brief"].get("deliverables") or [])
                + [str(sample["brief"].get("objective", ""))]
            ).lower()
            for phrase in forbidden:
                self.assertNotIn(
                    phrase, haystack, f"{sample.get('id')} promises {phrase!r}"
                )

    def test_every_sample_states_that_its_figures_are_illustrative(self) -> None:
        for sample in _load_samples():
            brief = sample["brief"]
            notes = " ".join(
                list(brief.get("warnings") or [])
                + list(brief.get("assumptions") or [])
                + [str(sample.get("additional_context") or "")]
            ).lower()
            self.assertTrue(
                "illustrative" in notes or "not a verified market rate" in notes,
                f"{sample.get('id')} does not mark its figures as illustrative",
            )

    def test_every_sample_is_labelled(self) -> None:
        for sample in _load_samples():
            self.assertIs(sample.get("sample"), True, sample.get("id"))


class SampleRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _shipped_ids(self) -> list[str]:
        return [sample["id"] for sample in _load_samples()]

    def test_first_run_seeds_the_shipped_samples(self) -> None:
        seeded = storage.seed_samples_on_first_run(self.data_dir)
        self.assertEqual([g["id"] for g in seeded], self._shipped_ids())
        self.assertTrue(all(g["sample"] for g in seeded))
        on_disk = storage.load_gigs(self.data_dir)
        self.assertEqual(on_disk, seeded)

    def test_refresh_updates_samples_and_leaves_real_gigs_alone(self) -> None:
        storage.seed_samples_on_first_run(self.data_dir)
        real = storage.add_gig(
            {"title": "A real published gig", "budget_inr": 500, "deadline": "3 days"},
            self.data_dir,
        )

        # Tamper with one sample and drop another, as stale runtime data would be.
        gigs = storage.load_gigs(self.data_dir)
        for gig in gigs:
            if gig.get("id") == "g_sample_0001":
                gig["title"] = "STALE SAMPLE TITLE"
            if gig.get("id") == "g_sample_0004":
                gig["title"] = "ANOTHER STALE TITLE"
        storage.save_gigs(gigs, self.data_dir)

        refreshed = storage.seed_samples_on_first_run(self.data_dir)

        by_id = {gig["id"]: gig for gig in refreshed}
        # The sample is restored to the shipped content.
        shipped_0001 = next(s for s in _load_samples() if s["id"] == "g_sample_0001")
        self.assertEqual(by_id["g_sample_0001"]["title"], shipped_0001["title"])
        # The real gig is byte-for-byte unchanged.
        self.assertEqual(by_id[real["id"]], real)
        # All shipped samples are present, and nothing else was invented.
        self.assertEqual(
            [g["id"] for g in refreshed if g.get("sample")], self._shipped_ids()
        )

    def test_refresh_is_idempotent_and_does_not_rewrite_when_unchanged(self) -> None:
        storage.seed_samples_on_first_run(self.data_dir)
        path = self.data_dir / "gigs.json"
        before = path.read_text(encoding="utf-8")
        storage.seed_samples_on_first_run(self.data_dir)
        storage.seed_samples_on_first_run(self.data_dir)
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_refresh_keeps_sample_ids_linked_to_applications(self) -> None:
        storage.seed_samples_on_first_run(self.data_dir)
        sample = storage.load_gigs(self.data_dir)[0]
        profile = {"id": "p_test", "display_name": "Test Student", "skills": ["Canva"]}
        application = applications.submit_application(
            profile,
            sample,
            "I can design the three Instagram posts with clear captions for the bakery.",
            data_dir=self.data_dir,
        )
        self.assertEqual(application["gig_id"], sample["id"])

        storage.seed_samples_on_first_run(self.data_dir)

        still_there = storage.get_gig(sample["id"], self.data_dir)
        self.assertIsNotNone(still_there)
        self.assertEqual(still_there["sample"], True)

    def test_a_user_file_without_samples_is_left_untouched(self) -> None:
        storage.save_gigs([{"id": "g_mine", "title": "Mine"}], self.data_dir)
        result = storage.seed_samples_on_first_run(self.data_dir)
        self.assertEqual(result, [{"id": "g_mine", "title": "Mine"}])
        self.assertEqual(storage.load_gigs(self.data_dir), [{"id": "g_mine", "title": "Mine"}])


class PublishedPassportConsistencyTests(unittest.TestCase):
    """What the business approved is exactly what the student view reads."""

    REQUEST = {
        "project_name": "Sunrise Bakery",
        "description": "Promote our new seasonal menu on Instagram.",
        "outcome": "More local customers visit the shop.",
        "budget": 800,
        "deadline": "2 days",
        "extra_context": "",
    }
    BRIEF = {
        "title": "Instagram posts for a bakery menu",
        "objective": "Promote the new seasonal menu to local families on Instagram.",
        "deliverables": ["Three ready-to-post images with captions"],
        "required_skills": ["Canva", "Copywriting"],
        "clarifying_questions": [],
        "acceptance_criteria": ["Three images with captions are delivered"],
        "assumptions": [],
        "warnings": [],
        "exclusions": ["Paid advertising is not included"],
        "client_responsibilities": ["Provide photos of the menu items"],
        "revision_expectations": ["One round of revisions"],
    }

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_student_view_reads_the_saved_passport_unchanged(self) -> None:
        record = gig_workflow.publish_gig(
            dict(self.BRIEF), dict(self.REQUEST), data_dir=self.data_dir
        )
        loaded = storage.get_gig(record["id"], self.data_dir)
        as_student = fairscope.passport_for_gig(loaded)

        self.assertEqual(as_student, record["passport"])
        self.assertEqual(
            as_student["sections"]["deliverables"]["value"], self.BRIEF["deliverables"]
        )
        self.assertEqual(
            as_student["sections"]["exclusions"]["value"], self.BRIEF["exclusions"]
        )
        # The published budget/deadline match the original request, unedited.
        self.assertEqual(as_student["sections"]["budget"]["value"], 800)
        self.assertEqual(as_student["sections"]["deadline"]["value"], "2 days")


if __name__ == "__main__":
    unittest.main()
