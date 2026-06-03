"""Tests for the test_provider_connection helper.

The helper must report failure for bad / missing keys and must NOT
silently fall through to the heuristic provider (the user needs to
know that *their* key is broken, not that the heuristic is fine).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from golem.summarizer import check_provider_connection


class TestProviderConnectionTests(unittest.TestCase):
    def test_heuristic_always_succeeds_without_a_key(self) -> None:
        ok, msg = check_provider_connection("heuristic", "")
        self.assertTrue(ok)
        self.assertIn("Heuristic", msg)

    def test_empty_key_on_real_provider_fails(self) -> None:
        ok, msg = check_provider_connection("groq", "")
        self.assertFalse(ok)
        self.assertIn("empty", msg.lower())

    def test_unknown_provider_fails(self) -> None:
        ok, msg = check_provider_connection("no_such_provider", "abc123")
        self.assertFalse(ok)
        self.assertIn("unknown", msg.lower())

    def test_bogus_key_does_not_silently_succeed(self) -> None:
        """A garbage key must surface as failure, not be masked by the heuristic fallback."""
        # We mock the network call to raise; the helper must NOT swallow it.
        with patch("golem.summarizer.OpenAICompatibleSummarizer") as MockSum:
            instance = MockSum.return_value
            instance.fallback = None  # helper will overwrite; just for clarity
            instance.get_file_metadata.side_effect = RuntimeError("401 Unauthorized")
            ok, msg = check_provider_connection("groq", "x" * 50)
            self.assertFalse(ok)
            self.assertIn("401", msg)

    def test_custom_openai_requires_base_url(self) -> None:
        ok, msg = check_provider_connection("custom_openai", "abc123", model="gpt-x", base_url="")
        self.assertFalse(ok)
        self.assertIn("base url", msg.lower())


if __name__ == "__main__":
    unittest.main()
