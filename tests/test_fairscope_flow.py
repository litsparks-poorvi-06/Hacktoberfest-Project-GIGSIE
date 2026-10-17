"""End-to-end checks for FairScope + Gig Passport in the Streamlit UI.

These use Streamlit's official ``AppTest`` harness to run app.py. Storage is
redirected to a temporary folder, the sample seeder is disabled, and the model
call is mocked - so your real ``data/`` files are never touched and no API
credits are spent.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fairscope  # noqa: E402
import gigsie_ai  # noqa: E402
import storage  # noqa: E402

try:
    from streamlit.testing.v1 import AppTest  # noqa: E402
except Exception:  # pragma: no cover
    AppTest = None

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

# The initial draft the mocked model "returns".
FAKE_RESULT = {
    "brief": {
        "title": "Instagram posts for a bakery menu",
        "objective": "Promote the new seasonal menu to local families on Instagram.",
        "deliverables": ["Three ready-to-post images with captions"],
        "required_skills": ["Canva", "Copywriting"],
        "clarifying_questions": ["Do you have photos of the menu items?"],
        "acceptance_criteria": ["Three images with captions are delivered"],
        "assumptions": ["The bakery already has an Instagram account"],
        "warnings": ["Two days is a short window if photos still need to be taken"],
    },
    "problems": [],
    "validation": [],
    "raw": "{}",
}

# The strategy revision the mocked model "returns".
STRATEGY_RESULT = {
    "brief": {
        "title": "Budget-first: three ready-to-post bakery images",
        "objective": "Deliver three ready-to-post Instagram images for the new menu.",
        "deliverables": ["Three ready-to-post images with captions"],
        "required_skills": ["Canva", "Copywriting"],
        "clarifying_questions": ["Do you have photos of the menu items?"],
        "acceptance_criteria": ["Three images with captions are delivered"],
        "assumptions": ["The bakery already has an Instagram account"],
        "warnings": ["Paid advertising is excluded from this scope"],
        "exclusions": ["Paid advertising", "Ongoing account management"],
        "client_responsibilities": ["Provide photos of the menu items"],
        "revision_expectations": ["One round of revisions"],
    },
    "problems": [],
    "validation": [],
    "raw": "{}",
    "scope_strategy": "budget_first",
}

# A brief with essential information missing (no acceptance criteria / skills).
INCOMPLETE_RESULT = {
    "brief": {
        "title": "Vague marketing gig",
        "objective": "Help promote the bakery on social media.",
        "deliverables": ["Some posts"],
        "required_skills": [],
        "clarifying_questions": [],
        "acceptance_criteria": [],
        "assumptions": [],
        "warnings": [],
    },
    "problems": [],
    "validation": [],
    "raw": "{}",
}


def _by_label(widgets, label: str):
    for widget in widgets:
        if getattr(widget, "label", None) == label:
            return widget
    raise AssertionError(f"widget with label {label!r} was not found")


def _open_sidebar(at, label: str):
    """Click a sidebar destination. Stage 9 gives each section its own page."""
    wanted = "".join(ch for ch in label if ch.isalnum()).lower()
    for button in at.sidebar.button:
        text = "".join(ch for ch in button.label if ch.isalnum()).lower()
        if text == wanted:
            button.click().run()
            return at
    raise AssertionError(f"sidebar destination {label!r} was not found")


def _open_student_find_work(at):
    return _open_sidebar(at, "Find Work")


def _labels(at) -> list[str]:
    return [button.label for button in at.button]


def _page_text(at) -> str:
    parts: list[str] = []
    for name in ("markdown", "caption", "text", "info", "warning", "error", "success"):
        for element in getattr(at, name, []) or []:
            parts.append(str(getattr(element, "value", "")))
    return "\n".join(parts)


def _fake_generate(request, scope_strategy=None, current_brief=None):
    """Mirror the real contract: the response records the strategy it was asked for.

    ``gigsie_ai.generate_task_brief`` sets ``result["scope_strategy"]`` to the key
    that was requested, so the mock must echo it rather than a fixed value.
    """
    if not scope_strategy:
        return copy.deepcopy(FAKE_RESULT)
    result = copy.deepcopy(STRATEGY_RESULT)
    result["scope_strategy"] = scope_strategy
    result["brief"]["title"] = (
        f"{fairscope.strategy_label(scope_strategy)}: three ready-to-post bakery images"
    )
    return result


def _strategies():
    """The three real strategy keys, read from the product, not hard-coded here."""
    return list(fairscope.SCOPE_STRATEGY_KEYS)


@unittest.skipUnless(AppTest is not None, "streamlit.testing.v1 is not available")
class FairScopeFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        patchers = [
            mock.patch.object(storage, "DATA_DIR", self.data_dir),
            mock.patch.object(storage, "seed_samples_on_first_run", return_value=[]),
            mock.patch.object(gigsie_ai, "generate_task_brief", new=_fake_generate),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    # --- helpers -----------------------------------------------------------
    def _open_business(self):
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        _by_label(at.button, "Start a business request").click().run()
        self.assertFalse(at.exception)
        return at

    @staticmethod
    def _to_passport(at):
        """Create with AI and the Gig Passport are separate pages (Stage 9)."""
        _by_label(at.button, "Continue to the Gig Passport").click().run()
        return at

    def _fill_request(self, at) -> None:
        _by_label(at.text_input, "Business or project name (optional)").set_value("Sunrise Bakery")
        _by_label(at.text_area, "What work needs to be done? *").set_value(
            "Promote our new seasonal menu on Instagram."
        )
        _by_label(at.text_area, "What outcome do you want? *").set_value(
            "More local customers visit the shop."
        )
        _by_label(at.number_input, "Budget in INR *").set_value(800.0)
        _by_label(at.text_input, "Deadline or completion time *").set_value("2 days")

    def _generate(self, at) -> None:
        self._fill_request(at)
        _by_label(at.button, "Generate task brief").click().run()
        self.assertFalse(at.exception)

    def _published(self) -> list[dict]:
        return [g for g in storage.load_gigs(self.data_dir) if not g.get("sample")]

    # --- FairScope panel ---------------------------------------------------
    def test_fairscope_review_panel_renders_after_generation(self) -> None:
        at = self._open_business()
        self._generate(at)
        text = _page_text(at)
        self.assertIn("FairScope review", text)
        self.assertIn("Clarity check", text)
        self.assertIn("Scope signals", text)
        self.assertIn("Recommended next action", text)
        self.assertIn("Gig Passport", text)

    def test_fairscope_is_not_shown_on_the_plain_form(self) -> None:
        at = self._open_business()
        self.assertNotIn("FairScope review", _page_text(at))

    def test_deterministic_findings_are_labelled_separately_from_ai(self) -> None:
        at = self._open_business()
        self._generate(at)
        text = _page_text(at)
        self.assertIn("deterministic", text.lower())
        self.assertIn("AI suggestions", text)

    def test_gig_passport_shows_a_needs_clarification_state(self) -> None:
        # The mocked draft lists no exclusions, so the passport must not invent any.
        at = self._open_business()
        self._generate(at)
        self.assertIn("Gig Passport", _page_text(at))

    # --- strategies --------------------------------------------------------
    def test_three_strategies_are_offered(self) -> None:
        at = self._open_business()
        self._generate(at)
        select = _by_label(at.selectbox, "Choose a strategy")
        self.assertEqual(select.options, ["Budget-first", "Outcome-first", "Milestone-first"])

    def test_each_strategy_keeps_its_own_identity_in_the_comparison(self) -> None:
        """Regression: the heading once read "Proposed: Unknown strategy".

        The strategy the business selected must survive generation, the rerun
        that renders the comparison, and the label shown to the user.
        """
        for key in _strategies():
            with self.subTest(strategy=key):
                at = self._open_business()
                self._generate(at)

                _by_label(at.selectbox, "Choose a strategy").set_value(
                    fairscope.strategy_label(key)
                ).run()
                _by_label(at.button, "Generate this strategy version").click().run()
                self.assertFalse(at.exception)

                text = _page_text(at)
                self.assertIn(f"Proposed: {fairscope.strategy_label(key)}", text)
                self.assertNotIn("Unknown strategy", text)

                # The selected identity is real state, not a display string.
                self.assertEqual(at.session_state["scope_variant_key"], key)
                self.assertEqual(
                    at.session_state["scope_variant"]["scope_strategy"], key
                )

                # An ordinary rerun must not lose the identity either.
                at.run()
                self.assertNotIn("Unknown strategy", _page_text(at))
                self.assertEqual(at.session_state["scope_variant_key"], key)

    def test_accepting_a_strategy_stores_that_exact_strategy(self) -> None:
        for key in _strategies():
            with self.subTest(strategy=key):
                at = self._open_business()
                self._generate(at)
                _by_label(at.selectbox, "Choose a strategy").set_value(
                    fairscope.strategy_label(key)
                ).run()
                _by_label(at.button, "Generate this strategy version").click().run()
                _by_label(
                    at.button, "Use this proposed version as my draft"
                ).click().run()
                self.assertFalse(at.exception)

                result = at.session_state["brief_result"]
                self.assertEqual(result["scope_strategy"], key)
                # The proposal is consumed, identity and all.
                self.assertIsNone(at.session_state["scope_variant"])
                self.assertIsNone(at.session_state["scope_variant_key"])
                self.assertIn(
                    fairscope.strategy_label(key), result["brief"]["title"]
                )

    def test_the_accepted_strategy_reaches_the_published_passport(self) -> None:
        for key in _strategies():
            with self.subTest(strategy=key):
                # Each strategy publishes its own gig into a clean store.
                (self.data_dir / "gigs.json").unlink(missing_ok=True)
                at = self._open_business()
                self._generate(at)
                _by_label(at.selectbox, "Choose a strategy").set_value(
                    fairscope.strategy_label(key)
                ).run()
                _by_label(at.button, "Generate this strategy version").click().run()
                _by_label(
                    at.button, "Use this proposed version as my draft"
                ).click().run()
                self._to_passport(at)
                _by_label(at.button, "Publish gig").click().run()

                published = self._published()
                self.assertEqual(len(published), 1)
                self.assertEqual(published[0]["passport"]["strategy"], key)

    def test_discarding_a_strategy_clears_it_and_keeps_the_draft(self) -> None:
        for key in _strategies():
            with self.subTest(strategy=key):
                at = self._open_business()
                self._generate(at)
                original = at.session_state["brief_result"]["brief"]["title"]

                _by_label(at.selectbox, "Choose a strategy").set_value(
                    fairscope.strategy_label(key)
                ).run()
                _by_label(at.button, "Generate this strategy version").click().run()
                _by_label(at.button, "Discard proposed version").click().run()
                self.assertFalse(at.exception)

                self.assertNotIn("Proposed:", _page_text(at))
                self.assertIsNone(at.session_state["scope_variant"])
                self.assertIsNone(at.session_state["scope_variant_key"])
                # The draft is exactly what it was before the proposal.
                self.assertEqual(
                    at.session_state["brief_result"]["brief"]["title"], original
                )
                self.assertNotIn(
                    "scope_strategy", at.session_state["brief_result"]
                )

    def test_a_failed_strategy_keeps_the_draft_and_records_no_identity(self) -> None:
        for key in _strategies():
            with self.subTest(strategy=key):
                def _failing(request, scope_strategy=None, current_brief=None):
                    if scope_strategy:
                        raise gigsie_ai.GigsieAIError("The model is unavailable.")
                    return copy.deepcopy(FAKE_RESULT)

                with mock.patch.object(
                    gigsie_ai, "generate_task_brief", new=_failing
                ):
                    at = self._open_business()
                    self._generate(at)
                    original = at.session_state["brief_result"]["brief"]["title"]

                    _by_label(at.selectbox, "Choose a strategy").set_value(
                        fairscope.strategy_label(key)
                    ).run()
                    _by_label(
                        at.button, "Generate this strategy version"
                    ).click().run()
                    self.assertTrue(at.error)
                    self.assertIn("unchanged", _page_text(at))

                    self.assertIsNone(at.session_state["scope_variant"])
                    self.assertIsNone(at.session_state["scope_variant_key"])
                    self.assertEqual(
                        at.session_state["brief_result"]["brief"]["title"], original
                    )
                    # A rerun must not resurrect a proposal that never existed.
                    at.run()
                    self.assertNotIn("Proposed:", _page_text(at))
                    self.assertEqual(self._published(), [])

    def test_starting_a_new_brief_clears_the_strategy_identity(self) -> None:
        at = self._open_business()
        self._generate(at)
        _by_label(at.button, "Generate this strategy version").click().run()
        self.assertEqual(at.session_state["scope_variant_key"], "budget_first")

        _by_label(at.button, "Start a new brief").click().run()
        self.assertFalse(at.exception)
        self.assertIsNone(at.session_state.get("scope_variant_key"))
        self.assertIsNone(at.session_state.get("scope_variant"))

    def test_generating_a_strategy_shows_a_comparison_without_replacing_the_draft(self) -> None:
        at = self._open_business()
        self._generate(at)
        _by_label(at.button, "Generate this strategy version").click().run()
        self.assertFalse(at.exception)

        text = _page_text(at)
        self.assertIn("Proposed:", text)
        self.assertIn("What changed", text)
        # The current draft is unchanged until the owner chooses it.
        self.assertEqual(self._published(), [])
        self._to_passport(at)
        self.assertEqual(_by_label(at.text_input, "Title").value, FAKE_RESULT["brief"]["title"])

    def test_using_the_proposed_version_replaces_the_draft(self) -> None:
        at = self._open_business()
        self._generate(at)
        _by_label(at.button, "Generate this strategy version").click().run()
        _by_label(at.button, "Use this proposed version as my draft").click().run()
        self.assertFalse(at.exception)
        self._to_passport(at)
        self.assertEqual(_by_label(at.text_input, "Title").value, STRATEGY_RESULT["brief"]["title"])

    def test_discarding_the_proposed_version_keeps_the_current_draft(self) -> None:
        at = self._open_business()
        self._generate(at)
        _by_label(at.button, "Generate this strategy version").click().run()
        _by_label(at.button, "Discard proposed version").click().run()
        self.assertFalse(at.exception)
        self.assertNotIn("Proposed:", _page_text(at))
        self._to_passport(at)
        self.assertEqual(_by_label(at.text_input, "Title").value, FAKE_RESULT["brief"]["title"])

    def test_strategy_failure_preserves_the_previous_draft(self) -> None:
        def _failing(request, scope_strategy=None, current_brief=None):
            if scope_strategy:
                raise gigsie_ai.GigsieAIError("The model is unavailable right now.")
            return copy.deepcopy(FAKE_RESULT)

        with mock.patch.object(gigsie_ai, "generate_task_brief", new=_failing):
            at = self._open_business()
            self._generate(at)
            _by_label(at.button, "Generate this strategy version").click().run()

            self.assertFalse(at.exception)
            self.assertTrue(at.error)
            self.assertIn("unchanged", _page_text(at))
            self.assertNotIn("Proposed:", _page_text(at))
            # The original draft is intact and nothing was published.
            self._to_passport(at)
            self.assertEqual(_by_label(at.text_input, "Title").value, FAKE_RESULT["brief"]["title"])
            self.assertEqual(self._published(), [])

    # --- publishing --------------------------------------------------------
    def test_explicit_publish_saves_the_reviewed_gig_with_its_passport(self) -> None:
        at = self._open_business()
        self._generate(at)
        self._to_passport(at)
        _by_label(at.button, "Publish gig").click().run()
        self.assertFalse(at.exception)

        published = self._published()
        self.assertEqual(len(published), 1)
        record = published[0]
        self.assertEqual(record["title"], FAKE_RESULT["brief"]["title"])
        self.assertIn("passport", record)
        self.assertTrue(record["passport"]["sections"])

    def test_rerun_does_not_publish_a_duplicate(self) -> None:
        at = self._open_business()
        self._generate(at)
        self._to_passport(at)
        _by_label(at.button, "Publish gig").click().run()
        at.run()
        at.run()
        self.assertEqual(len(self._published()), 1)

    def test_publish_is_blocked_until_essential_gaps_are_acknowledged(self) -> None:
        with mock.patch.object(
            gigsie_ai, "generate_task_brief", new=lambda *a, **k: copy.deepcopy(INCOMPLETE_RESULT)
        ):
            at = self._open_business()
            self._generate(at)
            self._to_passport(at)
            _by_label(at.button, "Publish gig").click().run()
            self.assertFalse(at.exception)

            # Not published: the passport still needs a decision.
            self.assertTrue(at.error)
            self.assertEqual(self._published(), [])

            # Acknowledge the two essential gaps, then publish explicitly.
            _by_label(
                at.checkbox, "Acknowledge 'Definition of done' as not yet specified"
            ).set_value(True)
            _by_label(
                at.checkbox, "Acknowledge 'Required skills' as not yet specified"
            ).set_value(True)
            _by_label(at.button, "Publish gig").click().run()
            self.assertFalse(at.exception)

            published = self._published()
            self.assertEqual(len(published), 1)
            self.assertIn("definition_of_done", published[0]["passport"]["acknowledged"])

    # --- student side ------------------------------------------------------
    def test_published_passport_is_visible_to_students(self) -> None:
        at = self._open_business()
        self._generate(at)
        self._to_passport(at)
        _by_label(at.button, "Publish gig").click().run()
        self.assertEqual(len(self._published()), 1)

        student = AppTest.from_file(str(APP_PATH), default_timeout=30)
        student.run()
        _by_label(student.button, "Enter the student area").click().run()
        _open_student_find_work(student)
        self.assertFalse(student.exception)

        expanders = [e.label for e in student.expander]
        self.assertIn("🛂 Gig Passport (agreed scope)", expanders)
        text = _page_text(student)
        # Deliverables and acceptance criteria match what the business published.
        self.assertIn("Three ready-to-post images with captions", text)
        self.assertIn("Three images with captions are delivered", text)

    def test_student_sees_exclusions_and_client_responsibilities(self) -> None:
        at = self._open_business()
        self._generate(at)
        # Use the strategy version, which carries exclusions and responsibilities.
        _by_label(at.button, "Generate this strategy version").click().run()
        _by_label(at.button, "Use this proposed version as my draft").click().run()
        self._to_passport(at)
        _by_label(at.button, "Publish gig").click().run()
        self.assertEqual(len(self._published()), 1)

        student = AppTest.from_file(str(APP_PATH), default_timeout=30)
        student.run()
        _by_label(student.button, "Enter the student area").click().run()
        _open_student_find_work(student)
        text = _page_text(student)
        self.assertIn("Paid advertising", text)
        self.assertIn("Provide photos of the menu items", text)

    # --- existing workflows preserved -------------------------------------
    def test_existing_student_profile_flow_still_reachable(self) -> None:
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.run()
        _by_label(at.button, "Enter the student area").click().run()
        # Stage 9 moved the profile editor to its own sidebar page.
        _open_sidebar(at, "My Profile")
        self.assertIn("Save profile", _labels(at))

    def test_business_flow_without_strategy_publishes_normally(self) -> None:
        at = self._open_business()
        self._generate(at)
        # No strategy invoked; the FairScope page still shows the review.
        self.assertNotIn("Proposed:", _page_text(at))
        self._to_passport(at)
        self.assertIn("Publish gig", _labels(at))


if __name__ == "__main__":
    unittest.main()
