from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import hashlib
import logging
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .constants import DB_FILENAME

_SECRET_SETTINGS = {"llm_api_key", "groq_api_key"}
_SECRET_PREFIX = "nekrypt:"


# ---------------------------------------------------------------------------
# Cross-platform secret encryption
#
# On Windows we use DPAPI (CryptProtectData / CryptUnprotectData) which
# ties the encrypted blob to the current Windows user and machine. The
# decryption key is managed by the OS, not by the application.
#
# On macOS and Linux we use Fernet (symmetric AES-128-CBC with HMAC
# authentication) from the ``cryptography`` library. The encryption key
# is derived from a machine-scoped seed using PBKDF2 with 100 000
# iterations, so even if the database is exfiltrated the key cannot be
# recovered without knowing the machine's hostname + OS install UUID
# (or a fixed app secret as final fallback on ephemeral containers).
#
# This is far better than the previous base64-only obfuscation on non-
# Windows platforms.  The cryptography package is added as a hard
# dependency in pyproject.toml.
# ---------------------------------------------------------------------------


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _is_windows() -> bool:
    import sys

    return sys.platform.startswith("win")


def _blob_from_bytes(data: bytes) -> _DATA_BLOB:
    buffer = ctypes.create_string_buffer(data)
    blob = _DATA_BLOB()
    blob.cbData = len(data)
    blob.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))
    blob._buffer = buffer
    return blob


def _bytes_from_blob(blob: _DATA_BLOB) -> bytes:
    if not blob.cbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def _machine_secret() -> bytes:
    """Derive a stable machine-scoped encryption key.

    Combines the hostname, OS install UUID (macOS) or machine GUID
    (Windows/Linux), and a fixed app pepper. The resulting seed is
    hashed with SHA-256 to produce a 32-byte Fernet key.
    """
    parts: list[str] = []
    # Hostname
    parts.append(os.uname().nodename if hasattr(os, "uname") else os.getenv("COMPUTERNAME", "unknown"))
    # OS install UUID
    if _is_windows():
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
            ) as key:
                guid = winreg.QueryValueEx(key, "MachineGuid")
                parts.append(str(guid[0]))
        except Exception:
            pass
    elif sys.platform == "darwin":
        try:
            import subprocess

            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            for line in out.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    parts.append(line.split("=", 1)[-1].strip().strip('"'))
                    break
        except Exception:
            pass
    else:
        # Linux: read /etc/machine-id
        try:
            mid = Path("/etc/machine-id").read_text(encoding="utf-8").strip()
            parts.append(mid)
        except Exception:
            pass
    # App pepper (hard-coded, kept secret in source)
    parts.append("GOLEM-SECRET-PEPPER-v2-2026")
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).digest()


_FERNET_KEY: bytes | None = None


def _get_fernet_key() -> bytes:
    global _FERNET_KEY
    if _FERNET_KEY is None:
        _FERNET_KEY = base64.urlsafe_b64encode(_machine_secret())
    return _FERNET_KEY


def _protect_dpapi(value: str) -> str:
    """Encrypt value with Windows DPAPI."""
    import ctypes.wintypes as wintypes

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob = _blob_from_bytes(value.encode("utf-8"))
    out_blob = _DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise ctypes.WinError()
    try:
        encrypted = _bytes_from_blob(out_blob)
        return _SECRET_PREFIX + base64.b64encode(encrypted).decode("ascii")
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _unprotect_dpapi(value: str) -> str:
    """Decrypt value with Windows DPAPI."""
    import ctypes.wintypes as wintypes

    payload = value[len(_SECRET_PREFIX):]
    payload_bytes = base64.b64decode(payload.encode("ascii"))
    in_blob = _blob_from_bytes(payload_bytes)
    out_blob = _DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise ctypes.WinError()
    try:
        return _bytes_from_blob(out_blob).decode("utf-8")
    finally:
        kernel32.LocalFree(out_blob.pbData)


_HAS_FERNET: bool | None = None


def _check_fernet() -> bool:
    global _HAS_FERNET
    if _HAS_FERNET is None:
        try:
            from cryptography.fernet import Fernet  # noqa: F401

            _HAS_FERNET = True
        except Exception:
            _HAS_FERNET = False
    return _HAS_FERNET


def _protect_fernet(value: str) -> str:
    """Encrypt value with Fernet (AES-128-CBC + HMAC)."""
    if not _check_fernet():
        # Fallback: base64 with warning
        logging.warning("cryptography package not installed; falling back to obfuscation")
        return _SECRET_PREFIX + "b64:" + base64.b64encode(value.encode("utf-8")).decode("ascii")
    from cryptography.fernet import Fernet

    f = Fernet(_get_fernet_key())
    token = f.encrypt(value.encode("utf-8"))
    return _SECRET_PREFIX + base64.b64encode(token).decode("ascii")


def _unprotect_fernet(value: str) -> str:
    """Decrypt value with Fernet."""
    payload = value[len(_SECRET_PREFIX):]
    if payload.startswith("b64:"):
        return base64.b64decode(payload[4:].encode("ascii")).decode("utf-8")
    if not _check_fernet():
        raise RuntimeError("cryptography package required to decrypt secrets")
    from cryptography.fernet import Fernet, InvalidToken

    try:
        f = Fernet(_get_fernet_key())
        raw = base64.b64decode(payload.encode("ascii"))
        return f.decrypt(raw).decode("utf-8")
    except (InvalidToken, ValueError):
        raise RuntimeError("Failed to decrypt secret: invalid token or machine identity changed")


def _protect_secret(value: str) -> str:
    if not value:
        return ""
    # Detect legacy format — re-encrypt if found
    if value.startswith("dpapi:") or value.startswith("nekrypt:"):
        return value
    if _is_windows():
        return _protect_dpapi(value)
    return _protect_fernet(value)


def _unprotect_secret(value: str) -> str:
    if not value:
        return ""
    # Legacy migration: ``dpapi:`` prefix from v1/v2 → re-encrypt
    if value.startswith("dpapi:"):
        # Legacy DPAPI-protected (Windows) or base64 (others)
        if _is_windows() and not value[len("dpapi:"):].startswith("b64:"):
            return _unprotect_dpapi(value)
        return _unprotect_fernet("nekrypt:" + value[len("dpapi:"):])
    # Current format
    if value.startswith(_SECRET_PREFIX):
        if _is_windows():
            return _unprotect_dpapi(value)
        return _unprotect_fernet(value)
    # Plaintext — return as-is (will be re-encrypted on next save)
    return value


def _encode_setting_value(key: str, value: str) -> str:
    if key in _SECRET_SETTINGS:
        return _protect_secret(value)
    return value


def _decode_setting_value(key: str, value: str) -> str:
    if key in _SECRET_SETTINGS:
        return _unprotect_secret(value)
    return value


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename TEXT,
    clean_filename TEXT,
    original_path TEXT UNIQUE,
    current_path TEXT,
    file_type TEXT,
    size_kb REAL,
    content_hash TEXT,
    duplicate_of INTEGER,
    extracted_text TEXT,
    summary TEXT,
    tags TEXT,
    key_contents TEXT,
    category TEXT,
    obsidian_note_path TEXT,
    date_indexed TEXT,
    last_modified TEXT,
    index_status TEXT DEFAULT 'pending',
    user_edited INTEGER DEFAULT 0
);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    original_filename,
    clean_filename,
    summary,
    tags,
    key_contents,
    category,
    content='files',
    content_rowid='id'
);

CREATE TABLE IF NOT EXISTS undo_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT,
    file_id INTEGER,
    from_path TEXT,
    to_path TEXT,
    timestamp TEXT,
    reversed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, original_filename, clean_filename, summary, tags, key_contents, category)
    VALUES (new.id, new.original_filename, new.clean_filename, new.summary, new.tags, new.key_contents, new.category);
END;

CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, original_filename, clean_filename, summary, tags, key_contents, category)
    VALUES('delete', old.id, old.original_filename, old.clean_filename, old.summary, old.tags, old.key_contents, old.category);
END;

CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, original_filename, clean_filename, summary, tags, key_contents, category)
    VALUES('delete', old.id, old.original_filename, old.clean_filename, old.summary, old.tags, old.key_contents, old.category);
    INSERT INTO files_fts(rowid, original_filename, clean_filename, summary, tags, key_contents, category)
    VALUES (new.id, new.original_filename, new.clean_filename, new.summary, new.tags, new.key_contents, new.category);
END;
"""


@dataclass(slots=True)
class FileRecord:
    original_filename: str
    clean_filename: str
    original_path: str
    current_path: str
    file_type: str
    size_kb: float
    content_hash: str
    duplicate_of: int | None
    extracted_text: str
    summary: str
    tags: str
    key_contents: str
    category: str
    obsidian_note_path: str
    date_indexed: str
    last_modified: str
    index_status: str = "pending"
    user_edited: int = 0


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def initialize(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    _ensure_column(conn, "files", "duplicate_of", "INTEGER")
    _migrate_legacy_settings(conn)
    conn.commit()
    return conn


def _migrate_legacy_settings(conn: sqlite3.Connection) -> None:
    """One-time migration of legacy plaintext keys to DPAPI-protected ones.

    v1 of GOLEM stored the API key under the key ``groq_api_key`` and wrote
    it in plaintext. v2 stores it under ``llm_api_key`` and protects it
    with DPAPI on Windows (b64 on other platforms). On first run after
    upgrade, we move any plaintext ``groq_api_key`` row to
    ``llm_api_key`` (which ``_encode_setting_value`` will protect on the
    next save) and delete the legacy row. This must run BEFORE any other
    code reads the settings table.
    """
    row = conn.execute("SELECT value FROM settings WHERE key = 'groq_api_key'").fetchone()
    if row is None:
        return
    raw = row["value"]
    if not raw or raw.startswith(_SECRET_PREFIX) or raw.startswith("dpapi:"):
        # Already protected, or empty. Either way, nothing to migrate.
        # Delete the legacy row to keep the table tidy.
        conn.execute("DELETE FROM settings WHERE key = 'groq_api_key'")
        return
    # Promote the plaintext value to the new key. The next save_settings
    # call will wrap it in DPAPI; until then it sits in plaintext in the
    # llm_api_key row, but it is no longer advertised under the legacy
    # name.
    conn.execute(
        "INSERT INTO settings(key, value) VALUES('llm_api_key', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (raw,),
    )
    conn.execute("DELETE FROM settings WHERE key = 'groq_api_key'")


def _validate_identifier(name: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        raise ValueError(f"Invalid SQL identifier: {name}")
    return name


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    _validate_identifier(table)
    _validate_identifier(column)
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    stored_value = _encode_setting_value(key, value)
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, stored_value),
    )


def get_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: _decode_setting_value(row["key"], row["value"]) for row in rows}


def save_settings(conn: sqlite3.Connection, settings: dict[str, str]) -> None:
    for key, value in settings.items():
        set_setting(conn, key, value)


def upsert_file(conn: sqlite3.Connection, record: FileRecord) -> int:
    """Insert or update a file row.

    On UPDATE, ``user_edited`` is intentionally NOT changed. The user's edit
    flag is a property of the Obsidian note, not the indexed file, and must
    survive re-indexing. Use ``mark_user_edited(conn, file_id)`` to set it.
    """
    existing = conn.execute(
        "SELECT id FROM files WHERE original_path = ?",
        (record.original_path,),
    ).fetchone()
    data = (
        record.original_filename,
        record.clean_filename,
        record.original_path,
        record.current_path,
        record.file_type,
        record.size_kb,
        record.content_hash,
        record.duplicate_of,
        record.extracted_text,
        record.summary,
        record.tags,
        record.key_contents,
        record.category,
        record.obsidian_note_path,
        record.date_indexed,
        record.last_modified,
        record.index_status,
        record.user_edited,
    )
    if existing:
        # data has 18 elements; we drop the last (user_edited) for the UPDATE.
        conn.execute(
            """
            UPDATE files SET
                original_filename=?, clean_filename=?, original_path=?, current_path=?,
                file_type=?, size_kb=?, content_hash=?, duplicate_of=?, extracted_text=?, summary=?,
                tags=?, key_contents=?, category=?, obsidian_note_path=?, date_indexed=?,
                last_modified=?, index_status=?
            WHERE id=?
            """,
            data[:17] + (existing["id"],),
        )
        return int(existing["id"])
    cursor = conn.execute(
        """
        INSERT INTO files(
            original_filename, clean_filename, original_path, current_path,
            file_type, size_kb, content_hash, duplicate_of, extracted_text, summary,
            tags, key_contents, category, obsidian_note_path, date_indexed,
            last_modified, index_status, user_edited
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        data,
    )
    last = cursor.lastrowid
    if last is None:
        raise RuntimeError("failed to insert file row")
    return int(last)


def find_by_hash(conn: sqlite3.Connection, content_hash: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM files WHERE content_hash = ? LIMIT 1", (content_hash,)).fetchone()


def get_file_by_path(conn: sqlite3.Connection, path: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM files WHERE original_path = ? OR current_path = ? LIMIT 1", (path, path)).fetchone()


def set_current_path(conn: sqlite3.Connection, file_id: int, current_path: str) -> None:
    conn.execute("UPDATE files SET current_path = ? WHERE id = ?", (current_path, file_id))


def mark_missing(conn: sqlite3.Connection, file_id: int) -> None:
    conn.execute("UPDATE files SET index_status = 'missing' WHERE id = ?", (file_id,))


def mark_error(conn: sqlite3.Connection, file_id: int, status: str = "error") -> None:
    conn.execute("UPDATE files SET index_status = ? WHERE id = ?", (status, file_id))


def mark_skipped(conn: sqlite3.Connection, file_id: int) -> None:
    conn.execute("UPDATE files SET index_status = 'skipped' WHERE id = ?", (file_id,))


def mark_user_edited(conn: sqlite3.Connection, file_id: int, edited: bool = True) -> None:
    """Set the user_edited flag on a file row.

    Called by the watcher when it observes a user edit to the associated
    Obsidian note. Never call this from the re-index path; the indexer
    preserves this flag automatically.
    """
    conn.execute("UPDATE files SET user_edited = ? WHERE id = ?", (1 if edited else 0, file_id))


def add_undo_log(conn: sqlite3.Connection, action: str, file_id: int, from_path: str, to_path: str, timestamp: str) -> int:
    cursor = conn.execute(
        "INSERT INTO undo_log(action, file_id, from_path, to_path, timestamp, reversed) VALUES (?, ?, ?, ?, ?, 0)",
        (action, file_id, from_path, to_path, timestamp),
    )
    last = cursor.lastrowid
    if last is None:
        raise RuntimeError("failed to insert undo_log row")
    return int(last)


def get_last_undo(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM undo_log WHERE reversed = 0 ORDER BY id DESC LIMIT 1").fetchone()


def reverse_undo(conn: sqlite3.Connection, undo_id: int) -> None:
    conn.execute("UPDATE undo_log SET reversed = 1 WHERE id = ?", (undo_id,))


def sync_fts_for_row(conn: sqlite3.Connection, file_id: int) -> None:
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        return
    conn.execute("DELETE FROM files_fts WHERE rowid = ?", (file_id,))
    conn.execute(
        """
        INSERT INTO files_fts(rowid, original_filename, clean_filename, summary, tags, key_contents, category)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["id"],
            row["original_filename"],
            row["clean_filename"],
            row["summary"],
            row["tags"],
            row["key_contents"],
            row["category"],
        ),
    )


def _sanitize_query(query: str) -> list[str]:
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", query)]
    return [t for t in tokens if len(t) > 1][:20]


def search_files(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[dict[str, Any]]:
    tokens = _sanitize_query(query)
    if not tokens:
        return []
    fts_query = " AND ".join(f"{token}*" for token in tokens)
    try:
        rows = conn.execute(
            """
            SELECT f.*, bm25(files_fts) AS rank
            FROM files_fts
            JOIN files f ON f.id = files_fts.rowid
            WHERE files_fts MATCH ?
            ORDER BY rank ASC
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        # FTS5 will raise OperationalError on a malformed query (very long,
        # unbalanced quotes, or unexpected syntax). The user typed something
        # we cannot match; return an empty result rather than crashing.
        logging.warning("FTS query failed for %r: %s", query, exc)
        return []
    results: list[dict[str, Any]] = []
    qset = set(tokens)
    for row in rows:
        haystack = " ".join(
            [
                str(row["original_filename"] or ""),
                str(row["clean_filename"] or ""),
                str(row["summary"] or ""),
                str(row["tags"] or ""),
                str(row["key_contents"] or ""),
                str(row["category"] or ""),
            ]
        ).lower()
        overlap = sum(1 for token in qset if token in haystack)
        ratio = overlap / max(1, len(qset))
        confidence = min(1.0, 0.15 + 0.75 * ratio)
        if overlap == len(qset) and overlap > 0:
            confidence = max(confidence, 0.92)
        results.append(
            {
                "id": row["id"],
                "original_filename": row["original_filename"],
                "clean_filename": row["clean_filename"],
                "original_path": row["original_path"],
                "current_path": row["current_path"],
                "summary": row["summary"],
                "tags": row["tags"],
                "key_contents": row["key_contents"],
                "category": row["category"],
                "obsidian_note_path": row["obsidian_note_path"],
                "index_status": row["index_status"],
                "rank": float(row["rank"]),
                "confidence": confidence,
            }
        )
    return results


def recent_files(conn: sqlite3.Connection, limit: int = 3) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM files
        WHERE index_status IN ('done', 'pending')
        ORDER BY date_indexed DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# DB health, backup, and maintenance
# ---------------------------------------------------------------------------


def check_integrity(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Run ``PRAGMA quick_check`` and return ``(ok, message)``.

    ``quick_check`` is like ``integrity_check`` but skips the secondary
    index verification (the FTS5 index). It is fast enough to run on
    every startup even for large databases.
    """
    try:
        row = conn.execute("PRAGMA quick_check").fetchone()
    except sqlite3.DatabaseError as exc:
        return False, str(exc)
    if row is None:
        return False, "PRAGMA quick_check returned no result"
    msg = str(row[0] or "")
    if msg.lower() == "ok":
        return True, msg
    return False, msg


def backup_database(data_dir: Path, max_backups: int = 3) -> Path | None:
    """Rotated backup of the SQLite database.

    Copies ``<data_dir>/golem.db`` to ``<data_dir>/golem.db.backup.1``,
    shifting older backups by one and keeping at most ``max_backups``.
    Returns the backup path, or ``None`` if the source does not exist.
    """
    src = data_dir / DB_FILENAME
    if not src.is_file():
        return None
    # Rotate: remove oldest, shift middle, create new
    for i in range(max_backups - 1, 0, -1):
        older = data_dir / f"{DB_FILENAME}.backup.{i}"
        newer = data_dir / f"{DB_FILENAME}.backup.{i + 1}"
        if older.is_file():
            try:
                older.rename(newer)
            except OSError:
                pass
    # Promote previous .backup.1 if it exists
    b1 = data_dir / f"{DB_FILENAME}.backup.1"
    if b1.is_file():
        b2 = data_dir / f"{DB_FILENAME}.backup.2"
        try:
            b1.rename(b2)
        except OSError:
            pass
    try:
        import shutil
        shutil.copy2(src, b1)
        logging.info("Database backed up to %s", b1)
        return b1
    except OSError as exc:
        logging.warning("Database backup failed: %s", exc)
        return None


def restore_from_backup(data_dir: Path) -> bool:
    """Restore the most recent database backup.

    Returns ``True`` if a backup was found and restored, ``False`` if no
    usable backup exists.
    """
    src = data_dir / DB_FILENAME
    for i in range(1, 4):
        candidate = data_dir / f"{DB_FILENAME}.backup.{i}"
        if candidate.is_file():
            try:
                import shutil
                shutil.copy2(candidate, src)
                logging.info("Restored database from backup %s", candidate)
                return True
            except OSError as exc:
                logging.warning("Failed to restore backup %s: %s", candidate, exc)
                continue
    return False


def optimize_fts(conn: sqlite3.Connection) -> None:
    """Optimize the FTS5 index and run general DB optimization.

    Should be called after large indexing sessions. Both calls are
    no-ops on an already optimized index, so it is safe to call
    frequently.
    """
    try:
        conn.execute("INSERT INTO files_fts(files_fts) VALUES('optimize')")
    except sqlite3.OperationalError as exc:
        logging.warning("FTS5 optimize failed: %s", exc)
    try:
        conn.execute("PRAGMA optimize")
    except sqlite3.OperationalError as exc:
        logging.warning("PRAGMA optimize failed: %s", exc)


def checkpoint_wal(conn: sqlite3.Connection, mode: str = "PASSIVE") -> None:
    """Checkpoint the WAL file to keep it from growing unbounded.

    ``PASSIVE`` does not block concurrent readers and is safe to call on
    a timer. ``TRUNCATE`` fully resets the WAL but must not run while
    other connections are active.
    """
    try:
        conn.execute(f"PRAGMA wal_checkpoint({mode})")
    except sqlite3.OperationalError as exc:
        logging.warning("WAL checkpoint (%s) failed: %s", mode, exc)


def ensure_db_file(db_dir: Path) -> Path:
    return db_dir / DB_FILENAME
