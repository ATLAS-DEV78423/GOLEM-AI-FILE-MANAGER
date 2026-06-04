"""Fuzz tests for the file text extractor.

The extractor must never crash on garbage input. A 100k-row index will
hit every malformed file format eventually, and a single crash takes
the whole scan down with it.
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from golem.extractor import extract_text


class ExtractorFuzzTests(unittest.TestCase):
    def test_extract_handles_random_bytes_for_every_supported_type(self) -> None:
        suffixes = [".pdf", ".docx", ".xlsx", ".txt"]
        rng = random.Random(0xC0FFEE)
        for _ in range(40):
            suffix = rng.choice(suffixes)
            data = rng.randbytes(rng.randint(0, 4096))
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(data)
                p = Path(f.name)
            try:
                text = extract_text(p)
                self.assertIsInstance(text, str)
            finally:
                p.unlink(missing_ok=True)

    def test_extract_handles_empty_file(self) -> None:
        for suffix in (".pdf", ".docx", ".xlsx", ".txt"):
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                p = Path(f.name)
            try:
                text = extract_text(p)
                self.assertEqual(text, "")
            finally:
                p.unlink(missing_ok=True)

    def test_extract_handles_over_size_file(self) -> None:
        # 50 MB is the cap; 51 MB must be skipped, returning "" without crash.
        cap_plus = 51 * 1024 * 1024
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"\x00" * cap_plus)
            p = Path(f.name)
        try:
            text = extract_text(p)
            self.assertEqual(text, "")
        finally:
            p.unlink(missing_ok=True)

    def test_extract_handles_unsupported_extension(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"some bytes")
            p = Path(f.name)
        try:
            self.assertEqual(extract_text(p), "")
        finally:
            p.unlink(missing_ok=True)

    def test_extract_handles_missing_file(self) -> None:
        self.assertEqual(extract_text(Path("/this/does/not/exist.pdf")), "")
        self.assertEqual(extract_text(Path("/this/does/not/exist.docx")), "")
        self.assertEqual(extract_text(Path("/this/does/not/exist.xlsx")), "")

    def test_extract_caps_txt_at_max_chars(self) -> None:
        """A 30 MB text file (under the 50 MB size cap) is truncated to
        ``_MAX_EXTRACT_CHARS`` so the FTS index and the LLM prompt are
        not poisoned with megabytes of text.
        """
        from golem.extractor import _MAX_EXTRACT_CHARS

        # 2 MB of 'a' repeated; the cap is 1 MB so we expect truncation.
        body = ("a" * (2 * 1024 * 1024)).encode("utf-8")
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(body)
            p = Path(f.name)
        try:
            text = extract_text(p)
            self.assertEqual(len(text), _MAX_EXTRACT_CHARS)
        finally:
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
