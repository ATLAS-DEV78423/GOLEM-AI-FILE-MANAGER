from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from typing import Callable

from .constants import SUPPORTED_EXTENSIONS, SYSTEM_SKIP_DIRS
from .extractor import extract_text
from .indexer import FileRecord, find_by_hash, mark_missing, set_current_path, transaction, upsert_file
from .organizer import organize_file, record_move
from .summarizer import BaseSummarizer
from .utils import humanize_filename, is_hidden_or_system_dir, sha256_file, text_excerpt
from .vault_writer import archive_orphan_note, read_user_edited, write_note


ProgressCallback = Callable[[float, str], None]
LogCallback = Callable[[str], None]


@dataclass(slots=True)
class ScanResult:
    processed: int = 0
    skipped: int = 0
    errors: int = 0


def iter_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not is_hidden_or_system_dir(d) and d not in SYSTEM_SKIP_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            yield path


def count_files(root: Path) -> int:
    return sum(1 for _ in iter_files(root))


def index_one_file(conn, path: Path, vault_folder: Path, summarizer: BaseSummarizer, dry_run: bool = False, log: LogCallback | None = None) -> tuple[int, str]:
    note_path: Path | None = None
    target_path: Path | None = None
    file_id: int | None = None
    try:
        content_hash = sha256_file(path) + f":{path.stat().st_size}"
        existing = find_by_hash(conn, content_hash)
        if existing and existing["original_path"] == str(path):
            return int(existing["id"]), "unchanged"

        text = extract_text(path)
        import datetime as _dt

        timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat()
        file_type = path.suffix.lower().lstrip(".")

        if existing and existing["original_path"] != str(path):
            duplicate_category = "Duplicates"
            metadata = summarizer.get_file_metadata(path.name, text_excerpt(text, 300))
            record = FileRecord(
                original_filename=path.name,
                clean_filename=metadata.clean_name,
                original_path=str(path),
                current_path=str(path),
                file_type=file_type,
                size_kb=path.stat().st_size / 1024.0,
                content_hash=content_hash,
                duplicate_of=int(existing["id"]),
                extracted_text=text_excerpt(text, 500),
                summary=str(existing["summary"] or metadata.summary),
                tags=str(existing["tags"] or ",".join(metadata.tags)),
                key_contents=str(existing["key_contents"] or metadata.key_contents),
                category=duplicate_category,
                obsidian_note_path=str(existing["obsidian_note_path"] or ""),
                date_indexed=timestamp,
                last_modified=timestamp,
                index_status="duplicate",
            )
            if dry_run:
                return 0, "dry_run"
            with transaction(conn):
                file_id = upsert_file(conn, record)
                target_path = organize_file(path, vault_folder, duplicate_category, dry_run=False)
                set_current_path(conn, file_id, str(target_path))
                conn.execute("UPDATE files SET current_path = ?, index_status = 'duplicate' WHERE id = ?", (str(target_path), file_id))
                record_move(conn, file_id, str(path), str(target_path))
            return file_id, "duplicate"

        if not text.strip():
            metadata = summarizer.get_file_metadata(path.name, "")
            record = FileRecord(
                original_filename=path.name,
                clean_filename=metadata.clean_name,
                original_path=str(path),
                current_path=str(path),
                file_type=file_type,
                size_kb=path.stat().st_size / 1024.0,
                content_hash=content_hash,
                duplicate_of=None,
                extracted_text="",
                summary=metadata.summary,
                tags=",".join(metadata.tags),
                key_contents=metadata.key_contents,
                category=metadata.category,
                obsidian_note_path="",
                date_indexed=timestamp,
                last_modified=timestamp,
                index_status="skipped",
            )
            with transaction(conn):
                file_id = upsert_file(conn, record)
            return file_id, "skipped"

        metadata = summarizer.get_file_metadata(path.name, text_excerpt(text, 300))
        record = FileRecord(
            original_filename=path.name,
            clean_filename=metadata.clean_name,
            original_path=str(path),
            current_path=str(path),
            file_type=file_type,
            size_kb=path.stat().st_size / 1024.0,
            content_hash=content_hash,
            duplicate_of=None,
            extracted_text=text_excerpt(text, 500),
            summary=metadata.summary,
            tags=",".join(metadata.tags),
            key_contents=metadata.key_contents,
            category=metadata.category,
            obsidian_note_path="",
            date_indexed=timestamp,
            last_modified=timestamp,
            index_status="pending",
        )
        if dry_run:
            return 0, "dry_run"
        note_path = write_note(vault_folder, record)
        record.obsidian_note_path = str(note_path)
        with transaction(conn):
            file_id = upsert_file(conn, record)
            target_path = organize_file(path, vault_folder, metadata.category, dry_run=False)
            set_current_path(conn, file_id, str(target_path))
            conn.execute("UPDATE files SET obsidian_note_path = ?, current_path = ?, index_status = 'done' WHERE id = ?", (str(note_path), str(target_path), file_id))
            record_move(conn, file_id, str(path), str(target_path))
        return file_id, "done"
    except Exception as exc:
        if target_path and target_path.exists():
            try:
                target_path.replace(path)
            except Exception:
                pass
        if note_path and note_path.exists():
            try:
                if not read_user_edited(note_path):
                    note_path.unlink()
            except Exception:
                pass
        if file_id is not None:
            try:
                with transaction(conn):
                    conn.execute("UPDATE files SET index_status = 'error' WHERE id = ?", (file_id,))
            except Exception:
                pass
        if log:
            log(f"Index error for {path}: {exc}")
        raise


def scan_folder(conn, watched_folder: Path, vault_folder: Path, summarizer: BaseSummarizer, progress: ProgressCallback | None = None, log: LogCallback | None = None, dry_run: bool = False) -> ScanResult:
    result = ScanResult()
    total = max(1, count_files(watched_folder))
    for index, path in enumerate(iter_files(watched_folder), start=1):
        if progress:
            progress(index / total, path.name)
        try:
            _, status = index_one_file(conn, path, vault_folder, summarizer, dry_run=dry_run, log=log)
            if status == "skipped":
                result.skipped += 1
            else:
                result.processed += 1
        except Exception:
            result.errors += 1
    reconcile_missing(conn, vault_folder)
    if progress:
        progress(1.0, "done")
    return result


def reconcile_missing(conn, vault_folder: Path) -> None:
    rows = conn.execute(
        "SELECT * FROM files WHERE index_status IN ('done', 'duplicate')"
    ).fetchall()
    for row in rows:
        current_path = Path(row["current_path"] or "")
        original_path = Path(row["original_path"] or "")
        if current_path.exists() or original_path.exists():
            continue
        with transaction(conn):
            mark_missing(conn, int(row["id"]))
        if row["obsidian_note_path"]:
            archive_orphan_note(vault_folder, str(row["obsidian_note_path"]))
