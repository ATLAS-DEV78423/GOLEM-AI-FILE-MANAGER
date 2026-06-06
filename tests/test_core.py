from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from golem.extractor import extract_text
from golem.indexer import (
    FileRecord,
    get_settings,
    initialize,
    save_settings,
    search_files,
    transaction,
    upsert_file,
)
from golem.legal import terms_of_service_text
from golem.scanner import index_one_file
from golem.search import SearchResponse, SearchResult
from golem.summarizer import HeuristicSummarizer, build_summarizer, provider_choices
from golem.vault_writer import archive_orphan_note, write_note
from installer import _ps_single_quoted


class CoreTests(unittest.TestCase):
    _sandbox: str = ""

    def setUp(self) -> None:
        self._sandbox = tempfile.mkdtemp()

    def tearDown(self) -> None:
        if self._sandbox:
            shutil.rmtree(self._sandbox, ignore_errors=True)

    def test_txt_extraction(self) -> None:
        path = Path(self._tmpdir()) / "note.txt"
        path.write_text("hello world", encoding="utf-8")
        self.assertIn("hello world", extract_text(path))

    def test_schema_and_search(self) -> None:
        db_path = Path(self._tmpdir()) / "golem.db"
        conn = initialize(db_path)
        record = FileRecord(
            original_filename="budget.pdf",
            clean_filename="Budget",
            original_path="C:/tmp/budget.pdf",
            current_path="C:/tmp/budget.pdf",
            file_type="pdf",
            size_kb=12.0,
            content_hash="abc:1",
            duplicate_of=None,
            extracted_text="budget report for march",
            summary="March budget report",
            tags="budget,finance",
            key_contents="budget, finance",
            category="Finance",
            obsidian_note_path="C:/vault/GOLEM/Budget.md",
            date_indexed="2026-05-31T00:00:00Z",
            last_modified="2026-05-31T00:00:00Z",
            index_status="done",
        )
        with transaction(conn):
            upsert_file(conn, record)
        results = search_files(conn, "march budget")
        self.assertTrue(results)
        self.assertEqual(results[0]["category"], "Finance")

    def test_heuristic_summarizer(self) -> None:
        summarizer = HeuristicSummarizer()
        metadata = summarizer.get_file_metadata(
            "invoice_2024.pdf", "Invoice for office supplies and payment due"
        )
        self.assertIn(metadata.category, {"Finance", "Other"})
        self.assertTrue(metadata.clean_name)

    def test_provider_registry_lists_major_backends(self) -> None:
        providers = {key for key, _ in provider_choices()}
        self.assertTrue(
            {
                "heuristic",
                "groq",
                "openai",
                "openrouter",
                "anthropic",
                "gemini",
                "xai",
                "nvidia_nim",
            }.issubset(providers)
        )

    def test_build_summarizer_without_key_uses_heuristics(self) -> None:
        summarizer = build_summarizer("openai", "", "", "")
        self.assertIsInstance(summarizer, HeuristicSummarizer)

    def test_terms_document_is_bundled(self) -> None:
        text = terms_of_service_text()
        self.assertIn("Disclaimer of Warranties", text)
        self.assertIn("MIT License", text)

    def test_pipeline_indexes_and_moves_file(self) -> None:
        watched = Path(self._tmpdir()) / "watched"
        vault = Path(self._tmpdir()) / "vault"
        watched.mkdir()
        vault.mkdir()
        source = watched / "budget.txt"
        source.write_text("budget report for march invoice payment", encoding="utf-8")
        conn = initialize(Path(self._tmpdir()) / "golem.db")
        file_id, status = index_one_file(conn, source, vault, HeuristicSummarizer())
        self.assertEqual(status, "done")
        self.assertEqual(file_id, 1)
        self.assertFalse(source.exists())
        self.assertTrue((vault / "GOLEM").exists())
        self.assertTrue((vault / "GOLEM Files" / "Finance" / "budget.txt").exists())

    def test_rollback_when_db_fails_after_move(self) -> None:
        """If the DB write fails after the on-disk move, the file must be
        moved back and the orphan note deleted (B2)."""
        watched = Path(self._tmpdir()) / "watched"
        vault = Path(self._tmpdir()) / "vault"
        watched.mkdir()
        vault.mkdir()
        source = watched / "report.txt"
        source.write_text("financial report for march", encoding="utf-8")
        db_path = Path(self._tmpdir()) / "golem.db"
        conn = initialize(db_path)

        # Force the DB transaction to fail by closing the connection first.
        # We patch upsert_file via monkey-patching to raise mid-transaction.
        from golem import scanner as scanner_mod

        original_upsert = scanner_mod.upsert_file

        def broken_upsert(*args, **kwargs):
            raise RuntimeError("simulated DB failure")

        scanner_mod.upsert_file = broken_upsert
        try:
            with self.assertRaises(RuntimeError):
                index_one_file(conn, source, vault, HeuristicSummarizer())
        finally:
            scanner_mod.upsert_file = original_upsert

        # Source file should be back at its original location (rollback worked).
        self.assertTrue(source.exists(), "rollback did not restore the source file")
        # And the row should be marked 'error' (file_id was 1, but the row
        # may not have been inserted because the broken_upsert fires before
        # the INSERT — we accept either: file_id is None and no row, or
        # file_id is set and status='error').
        rows = conn.execute("SELECT id, index_status FROM files").fetchall()
        for row in rows:
            self.assertEqual(row["index_status"], "error")

    def test_api_key_is_not_stored_in_plaintext(self) -> None:
        db_path = Path(self._tmpdir()) / "secure.db"
        conn = initialize(db_path)
        save_settings(
            conn,
            {
                "watched_folder": "C:/watched",
                "vault_folder": "C:/vault",
                "llm_provider": "groq",
                "llm_api_key": "super-secret-key",
                "groq_api_key": "super-secret-key",
                "terms_accepted": "1",
                "terms_version": "1.0",
            },
        )
        conn.commit()

        with sqlite3.connect(db_path) as conn2:
            raw_value = conn2.execute(
                "SELECT value FROM settings WHERE key = 'groq_api_key'"
            ).fetchone()[0]
        self.assertNotEqual(raw_value, "super-secret-key")
        self.assertTrue(
            str(raw_value).startswith("dpapi:") or str(raw_value).startswith("nekrypt:"),
            f"Expected dpapi: or nekrypt: prefix, got: {raw_value[:30]}...",
        )
        settings = get_settings(conn)
        self.assertEqual(settings["groq_api_key"], "super-secret-key")
        self.assertEqual(settings["llm_api_key"], "super-secret-key")

    def test_legacy_groq_api_key_is_migrated_to_llm_api_key(self) -> None:
        """On initialize, a plaintext groq_api_key row from a prior version
        must be moved to llm_api_key and the legacy row deleted."""
        db_path = Path(self._tmpdir()) / "legacy.db"
        # Simulate a v1 install: pre-existing tables, plaintext groq_api_key.
        with sqlite3.connect(db_path) as raw_conn:
            raw_conn.executescript(
                """
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
                INSERT INTO settings VALUES('watched_folder', 'C:/w');
                INSERT INTO settings VALUES('groq_api_key', 'plaintext-legacy-key');
                """
            )
            raw_conn.commit()
        # Re-open via initialize — this must run the migration.
        conn = initialize(db_path)
        keys = {row["key"] for row in conn.execute("SELECT key FROM settings").fetchall()}
        self.assertNotIn("groq_api_key", keys, "legacy key was not deleted")
        self.assertIn("llm_api_key", keys, "new key was not written")
        # The new row carries the plaintext (it will be re-protected on next save).
        row = conn.execute("SELECT value FROM settings WHERE key='llm_api_key'").fetchone()
        self.assertEqual(row["value"], "plaintext-legacy-key")
        # Round-trip: get_settings decodes protected values but the plaintext
        # passes through. Either way, the user sees the original key.
        settings = get_settings(conn)
        self.assertEqual(settings["llm_api_key"], "plaintext-legacy-key")

    def test_search_handles_malformed_fts_query(self) -> None:
        """A garbage query must not raise; it returns an empty list."""
        db_path = Path(self._tmpdir()) / "golem.db"
        conn = initialize(db_path)
        record = FileRecord(
            original_filename="alpha.txt",
            clean_filename="Alpha",
            original_path="C:/tmp/alpha.txt",
            current_path="C:/tmp/alpha.txt",
            file_type="txt",
            size_kb=1.0,
            content_hash="hash:1",
            duplicate_of=None,
            extracted_text="alpha",
            summary="alpha",
            tags="alpha",
            key_contents="alpha",
            category="Other",
            obsidian_note_path="",
            date_indexed="2026-01-01T00:00:00Z",
            last_modified="2026-01-01T00:00:00Z",
            index_status="done",
        )
        with transaction(conn):
            upsert_file(conn, record)
        # 1000-char token: still returns []
        big = "x" * 1000
        results = search_files(conn, big)
        self.assertEqual(results, [])
        # Empty / whitespace queries
        self.assertEqual(search_files(conn, ""), [])
        self.assertEqual(search_files(conn, "   "), [])

    def test_search_response_payload_handles_slots(self) -> None:
        response = SearchResponse(
            status="ok",
            results=[
                SearchResult(
                    id=1,
                    original_filename="alpha.txt",
                    clean_filename="Alpha",
                    original_path="C:/tmp/alpha.txt",
                    current_path="C:/tmp/alpha.txt",
                    summary="alpha",
                    tags="alpha",
                    key_contents="alpha",
                    category="Other",
                    obsidian_note_path="",
                    index_status="done",
                    confidence=0.9,
                    rank=0.1,
                )
            ],
        )
        payload = response.to_payload()
        self.assertEqual(payload["results"][0]["clean_filename"], "Alpha")

    def test_full_hash_detects_distinct_files(self) -> None:
        """Files that share a prefix but differ in the middle must not collide."""
        from golem.scanner import _content_hash

        a = Path(self._tmpdir()) / "a.bin"
        b = Path(self._tmpdir()) / "b.bin"
        a.write_bytes(b"\x01" * 200_000 + b"\x02" * 100)
        b.write_bytes(b"\x01" * 200_000 + b"\x03" * 100)
        # Same size, same first 64KB, different at offset 200_000
        self.assertEqual(a.stat().st_size, b.stat().st_size)
        h1 = _content_hash(a, a.stat().st_size)
        h2 = _content_hash(b, b.stat().st_size)
        self.assertNotEqual(h1, h2)

    def test_build_summarizer_falls_back_to_env_var(self) -> None:
        """If no key is passed to build_summarizer, the provider's env var is used."""
        import os

        from golem.summarizer import (
            PROVIDER_ENV_KEYS,
            AnthropicSummarizer,
            build_summarizer,
        )

        # Pick a provider that has an env var. We just need a key that's
        # not the heuristic provider.
        provider = "anthropic"
        env_var = PROVIDER_ENV_KEYS[provider]
        with unittest.mock.patch.dict(os.environ, {env_var: "env-var-key"}):
            summarizer = build_summarizer(provider, "", "", "")
        self.assertIsInstance(summarizer, AnthropicSummarizer)
        self.assertEqual(summarizer.api_key, "env-var-key")

    def test_search_rerank_path_comparison_is_case_insensitive(self) -> None:
        """The LLM rerank validator must accept paths in different case."""
        from golem.search import _normalize_path

        self.assertEqual(_normalize_path("C:\\Foo\\Bar.txt"), _normalize_path("c:/foo/bar.txt"))
        self.assertEqual(_normalize_path("C:\\Foo\\Bar.txt"), _normalize_path("C:\\FOO\\BAR.TXT"))
        self.assertNotEqual(_normalize_path("C:\\foo.txt"), _normalize_path("C:\\bar.txt"))

    def test_safe_move_falls_back_to_copy_when_move_raises(self) -> None:
        """When shutil.move raises any OSError, safe_move must copy+unlink."""
        from unittest.mock import patch

        from golem.utils import safe_move

        src = Path(self._tmpdir()) / "src.txt"
        dst = Path(self._tmpdir()) / "dst.txt"
        src.write_text("payload", encoding="utf-8")
        with patch("golem.utils.shutil.move", side_effect=OSError("simulated cross-volume")):
            safe_move(src, dst)
        self.assertTrue(dst.exists())
        self.assertEqual(dst.read_text(encoding="utf-8"), "payload")
        self.assertFalse(src.exists())

    def test_safe_move_raises_clear_error_if_unlink_fails(self) -> None:
        """If the source cannot be deleted after a successful copy,
        safe_move must surface a clear OSError."""
        from unittest.mock import patch

        from golem.utils import safe_move

        src = Path(self._tmpdir()) / "src.txt"
        dst = Path(self._tmpdir()) / "dst.txt"
        src.write_text("payload", encoding="utf-8")
        with (
            patch("golem.utils.shutil.move", side_effect=OSError("simulated cross-volume")),
            patch("golem.utils.Path.unlink", side_effect=OSError("permission denied")),
        ):
            with self.assertRaises(OSError) as ctx:
                safe_move(src, dst)
        self.assertIn("failed to delete the source", str(ctx.exception))

    def test_powershell_single_quote_escaping(self) -> None:
        self.assertEqual(_ps_single_quoted(r"C:\Users\O'Brien\GOLEM"), r"C:\Users\O''Brien\GOLEM")

    def test_note_writer_escapes_metadata(self) -> None:
        vault = Path(self._tmpdir()) / "vault"
        record = FileRecord(
            original_filename="report.md",
            clean_filename="report.md",
            original_path="C:/tmp/bad.txt",
            current_path="C:/tmp/bad.txt",
            file_type="txt",
            size_kb=1.0,
            content_hash="abc",
            duplicate_of=None,
            extracted_text="ignored",
            summary="summary\n---\nattack: yes",
            tags="alpha,beta\nextra",
            key_contents="key\ncontents",
            category="Other\nInjected",
            obsidian_note_path="",
            date_indexed="2026-05-31T00:00:00Z",
            last_modified="2026-05-31T00:00:00Z",
            index_status="pending",
        )
        note_path = write_note(vault, record)
        content = note_path.read_text(encoding="utf-8")
        self.assertNotIn("\nattack: yes", content)
        self.assertNotIn("---\nattack", content)
        self.assertIn("**Summary:** summary --- attack: yes", content)
        self.assertIn('golem_category: "Other Injected"', content)

    def test_orphan_archive_skips_user_edited_notes(self) -> None:
        vault = Path(self._tmpdir()) / "vault"
        note_dir = vault / "GOLEM"
        note_dir.mkdir(parents=True, exist_ok=True)
        note = note_dir / "note.md"
        note.write_text("---\nuser_edited: true\n---\nbody", encoding="utf-8")
        result = archive_orphan_note(vault, str(note))
        self.assertIsNone(result)
        self.assertTrue(note.exists())

    def test_upsert_preserves_user_edited_flag(self) -> None:
        """Re-indexing a file must NOT clear the user_edited flag (B7)."""
        db_path = Path(self._tmpdir()) / "golem.db"
        conn = initialize(db_path)
        original = FileRecord(
            original_filename="doc.txt",
            clean_filename="Doc",
            original_path="C:/tmp/doc.txt",
            current_path="C:/tmp/doc.txt",
            file_type="txt",
            size_kb=1.0,
            content_hash="hash-1",
            duplicate_of=None,
            extracted_text="",
            summary="v1 summary",
            tags="t1",
            key_contents="k1",
            category="Other",
            obsidian_note_path="",
            date_indexed="2026-01-01T00:00:00Z",
            last_modified="2026-01-01T00:00:00Z",
            index_status="done",
            user_edited=1,
        )
        with transaction(conn):
            file_id = upsert_file(conn, original)
        # Confirm flag is set
        row = conn.execute("SELECT user_edited FROM files WHERE id = ?", (file_id,)).fetchone()
        self.assertEqual(row["user_edited"], 1)
        # Now re-upsert with a fresh record that has user_edited=0
        updated = FileRecord(
            original_filename="doc.txt",
            clean_filename="Doc Renamed",
            original_path="C:/tmp/doc.txt",
            current_path="C:/tmp/doc.txt",
            file_type="txt",
            size_kb=2.0,
            content_hash="hash-1",
            duplicate_of=None,
            extracted_text="",
            summary="v2 summary",
            tags="t2",
            key_contents="k2",
            category="Finance",
            obsidian_note_path="C:/vault/note.md",
            date_indexed="2026-02-01T00:00:00Z",
            last_modified="2026-02-01T00:00:00Z",
            index_status="done",
            user_edited=0,
        )
        with transaction(conn):
            upsert_file(conn, updated)
        # user_edited must be preserved; other fields should have updated
        row = conn.execute(
            "SELECT user_edited, clean_filename, summary, size_kb, category FROM files WHERE id = ?",
            (file_id,),
        ).fetchone()
        self.assertEqual(row["user_edited"], 1, "user_edited flag was wiped on re-index")
        self.assertEqual(row["clean_filename"], "Doc Renamed")
        self.assertEqual(row["summary"], "v2 summary")
        self.assertEqual(row["category"], "Finance")

    def _tmpdir(self) -> str:
        return self._sandbox
