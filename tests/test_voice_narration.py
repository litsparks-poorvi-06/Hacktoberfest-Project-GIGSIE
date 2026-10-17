"""Tests for the Gigsie Voice Brief (ElevenLabs) and its UI integration.

Every test here is mocked or uses a temporary folder: **no API credit is ever
spent by the test suite**, and the real ``.env`` is never read or written.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import storage  # noqa: E402
import ui_common  # noqa: E402
import voice_narration  # noqa: E402

try:
    from streamlit.testing.v1 import AppTest  # noqa: E402
except Exception:  # pragma: no cover
    AppTest = None


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

FAKE_AUDIO = b"ID3\x03\x00\x00\x00fake-mpeg-bytes"

BRIEF = {
    "title": "Instagram posts for a bakery menu",
    "objective": "Promote the new seasonal menu to local families.",
    "deliverables": ["Three ready-to-post images with captions"],
    "required_skills": ["Canva", "Copywriting"],
    "acceptance_criteria": ["Three images with captions are delivered"],
}

REQUEST = {
    "project_name": "Sunrise Bakery",
    "description": "Promote our new seasonal menu on Instagram.",
    "outcome": "More local customers visit the shop.",
    "budget": 800,
    "deadline": "2 days",
}

GIG = {
    "id": "g_voice_0001",
    "title": "Design Instagram posts for a bakery",
    "business_name": "Sunrise Bakery",
    "budget_inr": 800,
    "deadline": "2 days",
    "brief": dict(BRIEF),
    "status": "open",
    "created_at": "2026-10-15T09:00:00+00:00",
    "sample": False,
}


def _voice_env(**extra):
    """Blanked or configured ElevenLabs values, leaving the rest of the env alone."""
    values = {
        "ELEVENLABS_API_KEY": "test-key-not-real",
        "ELEVENLABS_VOICE_ID": "voice123",
        "ELEVENLABS_MODEL_ID": "",
    }
    values.update(extra)
    return mock.patch.dict(os.environ, values, clear=False)


def _no_voice_env(**extra):
    values = {
        "ELEVENLABS_API_KEY": "",
        "ELEVENLABS_VOICE_ID": "",
        "ELEVENLABS_MODEL_ID": "",
    }
    values.update(extra)
    return mock.patch.dict(os.environ, values, clear=False)


class _FakeResponse(io.BytesIO):
    """Minimal stand-in for the object urlopen returns."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _patched_urlopen(payload: bytes = FAKE_AUDIO, recorder: list | None = None):
    """Patch urlopen so it records the request and returns ``payload``."""
    target = voice_narration.urllib.request.urlopen

    def _open(request, timeout=None):
        if recorder is not None:
            recorder.append({"request": request, "timeout": timeout})
        return _FakeResponse(payload)

    return mock.patch.object(voice_narration.urllib.request, "urlopen", _open)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class ConfigurationTests(unittest.TestCase):
    def test_missing_credentials_are_detected(self) -> None:
        with _no_voice_env():
            self.assertFalse(voice_narration.is_configured())
            note = voice_narration.configuration_note()
            self.assertIn("ELEVENLABS_API_KEY", note)
            self.assertIn("ELEVENLABS_VOICE_ID", note)

    def test_missing_only_the_key_is_reported(self) -> None:
        with _no_voice_env(ELEVENLABS_VOICE_ID="voice123"):
            self.assertFalse(voice_narration.is_configured())
            self.assertIn("ELEVENLABS_API_KEY", voice_narration.configuration_note())
            self.assertNotIn(
                "ELEVENLABS_VOICE_ID", voice_narration.configuration_note()
            )

    def test_both_values_configure_it(self) -> None:
        with _voice_env():
            self.assertTrue(voice_narration.is_configured())
            self.assertEqual(voice_narration.configuration_note(), "")

    def test_the_default_model_is_used_and_can_be_overridden(self) -> None:
        with _voice_env():
            self.assertEqual(voice_narration.model_id(), "eleven_multilingual_v2")
        with _voice_env(ELEVENLABS_MODEL_ID="eleven_turbo_v2"):
            self.assertEqual(voice_narration.model_id(), "eleven_turbo_v2")

    def test_the_note_never_contains_a_secret(self) -> None:
        with _no_voice_env():
            note = voice_narration.configuration_note()
        self.assertNotIn("xi-api-key", note.lower())
        self.assertNotIn("sk_", note)


# ---------------------------------------------------------------------------
# Request construction and audio handling
# ---------------------------------------------------------------------------
class RequestTests(unittest.TestCase):
    def test_request_shape_matches_the_elevenlabs_contract(self) -> None:
        with _voice_env():
            request = voice_narration.build_request("Hello from Gigsie.")
            headers = {k.lower(): v for k, v in request.header_items()}

        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            request.full_url,
            "https://api.elevenlabs.io/v1/text-to-speech/voice123",
        )
        self.assertEqual(headers["xi-api-key"], "test-key-not-real")
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["accept"], "audio/mpeg")

        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            body,
            {"text": "Hello from Gigsie.", "model_id": "eleven_multilingual_v2"},
        )

    def test_synthesize_returns_the_audio_bytes(self) -> None:
        calls: list = []
        with _voice_env():
            with _patched_urlopen(recorder=calls):
                audio = voice_narration.synthesize("Narrate this scope.")
        self.assertEqual(audio, FAKE_AUDIO)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["timeout"], voice_narration.DEFAULT_TIMEOUT_SECONDS)

    def test_text_is_trimmed_to_a_readable_length(self) -> None:
        with _voice_env():
            request = voice_narration.build_request("word " * 5000)
        body = json.loads(request.data.decode("utf-8"))
        self.assertLessEqual(len(body["text"]), voice_narration.MAX_CHARS + 1)
        self.assertTrue(body["text"].endswith("."))

    def test_empty_text_is_refused_before_any_request(self) -> None:
        with _voice_env():
            with mock.patch.object(
                voice_narration.urllib.request, "urlopen"
            ) as urlopen:
                with self.assertRaises(voice_narration.VoiceBriefError):
                    voice_narration.synthesize("   ")
        urlopen.assert_not_called()


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------
class FailureTests(unittest.TestCase):
    def test_http_error_becomes_a_friendly_error_without_the_key(self) -> None:
        error = urllib.error.HTTPError(
            "https://api.elevenlabs.io/v1/text-to-speech/voice123",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"detail":"invalid api key test-key-not-real"}'),
        )
        with _voice_env():
            with mock.patch.object(
                voice_narration.urllib.request, "urlopen", mock.Mock(side_effect=error)
            ):
                with self.assertRaises(voice_narration.VoiceBriefError) as ctx:
                    voice_narration.synthesize("Narrate this.")

        message = str(ctx.exception)
        self.assertIn("401", message)
        self.assertNotIn("test-key-not-real", message)
        self.assertNotIn("invalid api key", message)

    def test_timeout_is_reported_friendly(self) -> None:
        with _voice_env():
            with mock.patch.object(
                voice_narration.urllib.request,
                "urlopen",
                mock.Mock(side_effect=TimeoutError("too slow")),
            ):
                with self.assertRaises(voice_narration.VoiceBriefError) as ctx:
                    voice_narration.synthesize("Narrate this.")
        self.assertIn("timed out", str(ctx.exception).lower())

    def test_network_failure_is_reported_friendly(self) -> None:
        with _voice_env():
            with mock.patch.object(
                voice_narration.urllib.request,
                "urlopen",
                mock.Mock(side_effect=urllib.error.URLError("no route")),
            ):
                with self.assertRaises(voice_narration.VoiceBriefError) as ctx:
                    voice_narration.synthesize("Narrate this.")
        self.assertIn("elevenlabs", str(ctx.exception).lower())

    def test_empty_audio_is_not_reported_as_success(self) -> None:
        with _voice_env():
            with _patched_urlopen(b""):
                with self.assertRaises(voice_narration.VoiceBriefError):
                    voice_narration.synthesize("Narrate this.")

    def test_missing_key_makes_no_request_at_all(self) -> None:
        with _no_voice_env():
            with mock.patch.object(
                voice_narration.urllib.request, "urlopen"
            ) as urlopen:
                with self.assertRaises(voice_narration.VoiceBriefError):
                    voice_narration.synthesize("Narrate this.")
        urlopen.assert_not_called()


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------
class CacheKeyTests(unittest.TestCase):
    def test_identical_input_gives_an_identical_key(self) -> None:
        with _voice_env():
            first = voice_narration.narration_cache_key("Scope text", "voice123")
            second = voice_narration.narration_cache_key("Scope text", "voice123")
        self.assertEqual(first, second)

    def test_changing_the_text_invalidates_the_key(self) -> None:
        with _voice_env():
            first = voice_narration.narration_cache_key("One scope", "voice123")
            second = voice_narration.narration_cache_key("Another scope", "voice123")
        self.assertNotEqual(first, second)

    def test_changing_the_voice_invalidates_the_key(self) -> None:
        with _voice_env():
            first = voice_narration.narration_cache_key("Scope", "voice123")
            second = voice_narration.narration_cache_key("Scope", "voice999")
        self.assertNotEqual(first, second)

    def test_changing_the_model_invalidates_the_key(self) -> None:
        with _voice_env():
            first = voice_narration.narration_cache_key("Scope", "voice123", "eleven_a")
            second = voice_narration.narration_cache_key("Scope", "voice123", "eleven_b")
        self.assertNotEqual(first, second)


# ---------------------------------------------------------------------------
# Narration built from the real saved scope
# ---------------------------------------------------------------------------
class NarrationContentTests(unittest.TestCase):
    def test_fairscope_narration_uses_the_actual_brief_and_request(self) -> None:
        import fairscope

        analysis = fairscope.analyze_brief(REQUEST, BRIEF)
        text = voice_narration.build_fairscope_narration(
            brief=BRIEF, request=REQUEST, analysis=analysis
        )

        self.assertIn("Sunrise Bakery", text)
        self.assertIn(BRIEF["title"], text)
        self.assertIn("Three ready-to-post images with captions", text)
        self.assertIn("Canva", text)
        self.assertIn("800 rupees", text)
        self.assertIn("2 days", text)
        # It is a draft, and it says so.
        self.assertIn("draft", text.lower())

    def test_fairscope_narration_does_not_invent_a_budget(self) -> None:
        text = voice_narration.build_fairscope_narration(
            brief=BRIEF, request={"budget": 0, "deadline": ""}
        )
        self.assertIn("No budget or deadline", text)

    def test_passport_narration_uses_the_actual_gig_and_passport(self) -> None:
        import fairscope

        passport = fairscope.build_passport(BRIEF, REQUEST)
        text = voice_narration.build_passport_narration(gig=GIG, passport=passport)

        self.assertIn(GIG["title"], text)
        self.assertIn("Sunrise Bakery", text)
        self.assertIn("800", text)
        self.assertIn("2 days", text)
        self.assertIn("Three ready-to-post images with captions", text)

    def test_passport_narration_marks_unconfirmed_sections(self) -> None:
        text = voice_narration.build_passport_narration(
            gig={"title": "Bare gig"},
            passport={
                "sections": {"objective": {"needs_clarification": True, "value": []}}
            },
        )
        self.assertIn("No objective has been written yet", text)

    def test_narration_is_bounded_in_length(self) -> None:
        huge = dict(
            BRIEF,
            deliverables=[f"Deliverable number {index}" for index in range(500)],
        )
        text = voice_narration.build_fairscope_narration(brief=huge, request=REQUEST)
        self.assertLessEqual(len(text), voice_narration.MAX_CHARS + 1)


# ---------------------------------------------------------------------------
# UI integration: no request until asked, then exactly one per text
# ---------------------------------------------------------------------------
@unittest.skipUnless(AppTest, "Streamlit AppTest is unavailable")
class VoiceBriefUITests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        for patcher in (
            mock.patch.object(storage, "DATA_DIR", self.data_dir),
            mock.patch.object(storage, "seed_samples_on_first_run", return_value=[]),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        storage.save_gigs([GIG], data_dir=self.data_dir)

    def _open_find_work(self):
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.session_state["view"] = ui_common.VIEW_STUDENT
        at.session_state["section"] = ui_common.SEC_FIND_WORK
        at.run()
        self.assertFalse(at.exception)
        return at

    @staticmethod
    def _click(at, label):
        for button in at.button:
            if button.label == label:
                button.click().run()
                return True
        return False

    def test_unconfigured_voice_brief_does_not_break_the_page(self) -> None:
        with _no_voice_env():
            at = self._open_find_work()

        self.assertFalse(at.exception)
        # The action is replaced by a quiet setup note instead of a dead button.
        self.assertNotIn(
            "Listen to this Gig Passport", [b.label for b in at.button]
        )
        text = " ".join(m.value for m in at.markdown)
        self.assertIn("Voice Brief is not configured", text)
        # The gig itself still rendered: nothing else was affected.
        self.assertIn("Design Instagram posts for a bakery", text)

    def test_no_request_before_the_button_is_clicked(self) -> None:
        with _voice_env():
            with mock.patch.object(
                voice_narration, "synthesize", return_value=FAKE_AUDIO
            ) as synthesize:
                at = self._open_find_work()
                at.run()  # an ordinary rerun, as a page refresh would cause

        self.assertFalse(at.exception)
        synthesize.assert_not_called()

    def test_one_request_per_text_across_reruns(self) -> None:
        with _voice_env():
            with mock.patch.object(
                voice_narration, "synthesize", return_value=FAKE_AUDIO
            ) as synthesize:
                at = self._open_find_work()
                self.assertTrue(
                    self._click(at, "Listen to this Gig Passport"),
                    "the voice action should be offered when configured",
                )
                self.assertEqual(synthesize.call_count, 1)

                # Ordinary reruns reuse the cached clip: no second request.
                at.run()
                at.run()
                self.assertEqual(synthesize.call_count, 1)

    def test_a_generation_failure_shows_an_error_and_keeps_the_page(self) -> None:
        with _voice_env():
            with mock.patch.object(
                voice_narration,
                "synthesize",
                side_effect=voice_narration.VoiceBriefError(
                    "ElevenLabs is unavailable."
                ),
            ):
                at = self._open_find_work()
                self._click(at, "Listen to this Gig Passport")

        self.assertFalse(at.exception)
        self.assertTrue(
            any("ElevenLabs is unavailable." in e.value for e in at.error)
        )
        # The gig detail is untouched by the narration failure.
        text = " ".join(m.value for m in at.markdown)
        self.assertIn("Design Instagram posts for a bakery", text)


if __name__ == "__main__":
    unittest.main()
