"""Tests for the test_provider_connection helper.

The helper must report failure for bad / missing keys and must NOT
silently fall through to the heuristic provider (the user needs to
know that *their* key is broken, not that the heuristic is fine).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from golem.summarizer import OpenAICompatibleSummarizer, check_provider_connection


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
        # check_provider_connection calls _chat_completion directly (not get_file_metadata).
        with patch("golem.summarizer.OpenAICompatibleSummarizer") as MockSum:
            instance = MockSum.return_value
            instance.fallback = None  # helper will overwrite; just for clarity
            instance._chat_completion.side_effect = RuntimeError("401 Unauthorized")
            ok, msg = check_provider_connection("groq", "x" * 50)
            self.assertFalse(ok)
            self.assertIn("401", msg)

    def test_custom_openai_requires_base_url(self) -> None:
        ok, msg = check_provider_connection("custom_openai", "abc123", model="gpt-x", base_url="")
        self.assertFalse(ok)
        self.assertIn("base url", msg.lower())

    def test_metadata_prompt_mentions_document_classification(self) -> None:
        captured: dict[str, str] = {}

        class _Probe(OpenAICompatibleSummarizer):
            def _chat_completion(self, system_prompt: str, user_prompt: str, model: str) -> str:  # type: ignore[override]
                captured["system"] = system_prompt
                captured["user"] = user_prompt
                return (
                    '{"summary":"A guide about prompt engineering","tags":["guide","prompts"],'
                    '"key_contents":"prompt engineering","category":"Other","clean_name":"Guide"}'
                )

        summarizer = _Probe(api_key="k", model="m", base_url="https://example.com/v1")
        summarizer.get_file_metadata("fabric-notes.md", "Prompt examples and workflow notes")

        self.assertIn("local document understanding engine", captured["system"])
        self.assertIn("guide, prompt library entry", captured["user"])
        self.assertIn("Return JSON only", captured["user"])

    def test_rerank_prompt_prefers_semantic_intent(self) -> None:
        captured: dict[str, str] = {}

        class _Probe(OpenAICompatibleSummarizer):
            def _chat_completion(self, system_prompt: str, user_prompt: str, model: str) -> str:  # type: ignore[override]
                captured["system"] = system_prompt
                captured["user"] = user_prompt
                return "C:/vault/GOLEM Files/Other/example.md"

        summarizer = _Probe(api_key="k", model="m", base_url="https://example.com/v1")
        result = summarizer.search_rerank(
            "find the Fabric prompt for summarizing PDFs",
            [
                {
                    "current_path": "C:/vault/GOLEM Files/Other/example.md",
                    "summary": "a prompt library",
                },
            ],
        )

        self.assertEqual(result, "C:/vault/GOLEM Files/Other/example.md")
        self.assertIn("search reranker", captured["system"])
        self.assertIn("Prefer semantic intent over keyword overlap.", captured["user"])


if __name__ == "__main__":
    unittest.main()
