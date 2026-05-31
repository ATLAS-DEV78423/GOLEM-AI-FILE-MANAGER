from __future__ import annotations

from pathlib import Path
import sqlite3
import unittest

from golem.extractor import extract_text
from golem.legal import terms_of_service_text
from golem.indexer import FileRecord, get_settings, initialize, save_settings, search_files, transaction, upsert_file
from golem.scanner import index_one_file
from golem.summarizer import HeuristicSummarizer, build_summarizer, provider_choices
from golem.vault_writer import archive_orphan_note, write_note
from installer import _ps_single_quoted


class CoreTests(unittest.TestCase):
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
        metadata = summarizer.get_file_metadata("invoice_2024.pdf", "Invoice for office supplies and payment due")
        self.assertIn(metadata.category, {"Finance", "Other"})
        self.assertTrue(metadata.clean_name)

    def test_provider_registry_lists_major_backends(self) -> None:
        providers = {key for key, _ in provider_choices()}
        self.assertTrue({"heuristic", "groq", "openai", "openrouter", "anthropic", "gemini", "xai", "nvidia_nim"}.issubset(providers))

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
            raw_value = conn2.execute("SELECT value FROM settings WHERE key = 'groq_api_key'").fetchone()[0]
        self.assertNotEqual(raw_value, "super-secret-key")
        self.assertTrue(str(raw_value).startswith("dpapi:"))
        settings = get_settings(conn)
        self.assertEqual(settings["groq_api_key"], "super-secret-key")
        self.assertEqual(settings["llm_api_key"], "super-secret-key")

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
            summary='summary\n---\nattack: yes',
            tags='alpha,beta\nextra',
            key_contents='key\ncontents',
            category='Other\nInjected',
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

    def _tmpdir(self) -> str:
        if not hasattr(self, "_sandbox"):
            import tempfile

            self._sandbox = tempfile.mkdtemp()
        return self._sandbox
