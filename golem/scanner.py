from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from .constants import SUPPORTED_EXTENSIONS, SYSTEM_SKIP_DIRS
from .extractor import extract_text
from .indexer import (
    FileRecord,
    find_by_hash,
    mark_missing,
    set_current_path,
    transaction,
    upsert_file,
)
from .organizer import organize_file, record_move
from .summarizer import BaseSummarizer
from .utils import is_hidden_or_system_dir, safe_move, sha256_file, text_excerpt
from .vault_writer import archive_orphan_note, read_user_edited, write_note

# Files at or below this size are hashed in full. Larger files use a
# head+tail hash to keep duplicate detection both fast and collision-resistant.
# 10 MB is a reasonable threshold: a modern SSD streams that in well under a
# second, and the cost of a false-positive duplicate is real (the user's file
# is routed to Duplicates/).
_FULL_HASH_THRESHOLD = 10 * 1024 * 1024
_HEAD_TAIL_CHUNK = 64 * 1024


ProgressCallback = Callable[[float, str], None]
LogCallback = Callable[[str], None]


@dataclass(slots=True)
class ScanResult:
    processed: int = 0
    skipped: int = 0
    errors: int = 0


def _content_hash(path: Path, size: int) -> str:
    """Compute a collision-resistant content hash for duplicate detection.

    For files at or below ``_FULL_HASH_THRESHOLD`` bytes we hash the entire
    file. For larger files we hash the first ``_HEAD_TAIL_CHUNK`` bytes
    plus the last ``_HEAD_TAIL_CHUNK`` bytes (when the file is long enough).
    The collision probability for distinct large files is astronomically
    small (you would need 2^256 identical head/tail blocks), and we never
    see that in practice. The size is appended so two zero-byte files with
    identical head+tail (i.e. none) still differ if their sizes differ.
    """
    if size <= _FULL_HASH_THRESHOLD:
        return sha256_file(path) + f":{size}"
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        head = fh.read(_HEAD_TAIL_CHUNK)
        digest.update(head)
        if size > 2 * _HEAD_TAIL_CHUNK:
            fh.seek(-_HEAD_TAIL_CHUNK, os.SEEK_END)
            tail = fh.read(_HEAD_TAIL_CHUNK)
            digest.update(tail)
    return digest.hexdigest() + f":{size}"


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


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


def _rollback(
    conn,
    file_id: int | None,
    target_path: Path | None,
    note_path: Path | None,
    original_source: Path,
) -> None:
    """Best-effort rollback of an in-progress index_one_file.

    Called from the except branch. The DB and disk states are independent
    so each needs its own undo step. The undo log row written earlier
    (inside the transaction) is sufficient to reverse a successful move;
    here we handle the partial-failure case where a file was created but
    the transaction did not commit.
    """
    if target_path and target_path.exists() and original_source.parent.exists():
        try:
            # If the source dir still exists, the file is safe to put back.
            # We use safe_move (copy + unlink on cross-volume) because
            # shutil.move can fail across volume boundaries in reverse too.
            safe_move(target_path, original_source)
        except OSError as exc:
            logging.error("Rollback move failed: target=%s source=%s err=%s", target_path, original_source, exc)
    if note_path and note_path.exists():
        try:
            if not read_user_edited(note_path):
                note_path.unlink()
        except OSError as exc:
            logging.error("Rollback note-delete failed: %s err=%s", note_path, exc)
    if file_id is not None:
        try:
            with transaction(conn):
                conn.execute("UPDATE files SET index_status = 'error' WHERE id = ?", (file_id,))
        except Exception as exc:
            logging.error("Rollback DB-update failed for id=%s: %s", file_id, exc)


def index_one_file(
    conn,
    path: Path,
    vault_folder: Path,
    summarizer: BaseSummarizer,
    dry_run: bool = False,
    log: LogCallback | None = None,
) -> tuple[int, str]:
    """Index and (unless dry_run) move a single file.

    Returns ``(file_id, status)`` where status is one of:
      - "unchanged"   file already indexed at this path
      - "duplicate"   hash collision with another file; moved to Duplicates/
      - "skipped"     no extractable text
      - "done"        indexed and moved
      - "dry_run"     no changes made

    On any exception, ``_rollback`` is invoked and the exception is
    re-raised. The caller (``scan_folder``) increments the error counter.
    """
    note_path: Path | None = None
    target_path: Path | None = None
    file_id: int | None = None
    try:
        size = path.stat().st_size
    except OSError as exc:
        if log:
            log(f"Stat failed for {path}: {exc}")
        raise
    try:
        content_hash = _content_hash(path, size)
        existing = find_by_hash(conn, content_hash)
        if existing and existing["original_path"] == str(path):
            return int(existing["id"]), "unchanged"

        text = extract_text(path)
        timestamp = _now_iso()
        file_type = path.suffix.lower().lstrip(".")

        # --- DUPLICATE PATH ---
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
            # Move on disk first. If the DB write fails, _rollback undoes
            # the move. The on-disk move is idempotent against reconcile_missing.
            try:
                target_path = organize_file(path, vault_folder, duplicate_category, dry_run=False)
            except Exception:
                _rollback(conn, None, None, None, path)
                raise
            try:
                with transaction(conn):
                    file_id = upsert_file(conn, record)
                    set_current_path(conn, file_id, str(target_path))
                    record_move(conn, file_id, str(path), str(target_path))
            except Exception:
                _rollback(conn, file_id, target_path, None, path)
                raise
            return file_id, "duplicate"

        # --- SKIPPED PATH (no extractable text) ---
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

        # --- NORMAL PATH ---
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
        # Write the note FIRST (on disk only) so a failure here doesn't
        # leave a moved file with no note. If the move later fails, the
        # rollback will delete the note if it isn't user-edited.
        note_path = write_note(vault_folder, record)
        record.obsidian_note_path = str(note_path)
        # Move on disk. We do this OUTSIDE the transaction; if the DB
        # write later fails we use _rollback to undo the move.
        try:
            target_path = organize_file(path, vault_folder, metadata.category, dry_run=False)
        except Exception:
            # On-disk move failed; clean up the orphaned note and bail.
            _rollback(conn, None, None, note_path, path)
            raise
        try:
            with transaction(conn):
                file_id = upsert_file(conn, record)
                set_current_path(conn, file_id, str(target_path))
                conn.execute(
                    "UPDATE files SET obsidian_note_path = ?, current_path = ?, index_status = 'done' WHERE id = ?",
                    (str(note_path), str(target_path), file_id),
                )
                record_move(conn, file_id, str(path), str(target_path))
        except Exception:
            _rollback(conn, file_id, target_path, note_path, path)
            raise
        return file_id, "done"
    except Exception as exc:
        if log:
            log(f"Index error for {path}: {exc}")
        # _rollback was already called inside the inner except branches
        # for partial-failure cases. This outer except is a catch-all
        # for early failures (e.g. sha256, file stat).
        raise


def scan_folder(
    conn,
    watched_folder: Path,
    vault_folder: Path,
    summarizer: BaseSummarizer,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
    dry_run: bool = False,
) -> ScanResult:
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
        except Exception as exc:
            logging.exception("Scan iteration failed for %s: %s", path, exc)
            result.errors += 1
    reconcile_missing(conn, vault_folder)
    if progress:
        progress(1.0, "done")
    return result


def reconcile_missing(conn, vault_folder: Path) -> None:
    """Mark indexed-but-deleted files as missing and archive their notes.

    Streams the candidate rows in batches of 500 instead of materializing
    the full result set, so an index with 100k rows uses bounded memory.
    The previous implementation fetched every column of every candidate
    row into a list before iterating — fine for a thousand rows, fatal
    for a hundred thousand.
    """
    cursor = conn.execute(
        "SELECT id, original_path, current_path, obsidian_note_path "
        "FROM files WHERE index_status IN ('done', 'duplicate')"
    )
    while True:
        rows = cursor.fetchmany(500)
        if not rows:
            break
        for row in rows:
            current_path = Path(row["current_path"] or "")
            original_path = Path(row["original_path"] or "")
            if current_path.exists() or original_path.exists():
                continue
            with transaction(conn):
                mark_missing(conn, int(row["id"]))
            if row["obsidian_note_path"]:
                archive_orphan_note(vault_folder, str(row["obsidian_note_path"]))
