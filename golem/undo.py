from __future__ import annotations

import shutil
import logging
from pathlib import Path

from .indexer import get_last_undo, reverse_undo, set_current_path, transaction
from .vault_writer import read_user_edited


def undo_last(conn, vault_folder: Path) -> dict[str, str]:
    row = get_last_undo(conn)
    if row is None:
        return {"status": "empty", "message": "No undoable actions found."}
    from_path = Path(row["from_path"])
    to_path = Path(row["to_path"])
    if not to_path.exists():
        with transaction(conn):
            reverse_undo(conn, int(row["id"]))
        return {"status": "missing", "message": "Latest moved file no longer exists."}
    from_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(to_path), str(from_path))
    file_row = conn.execute("SELECT * FROM files WHERE id = ?", (row["file_id"],)).fetchone()
    note_path = Path(file_row["obsidian_note_path"]) if file_row and file_row["obsidian_note_path"] else None
    with transaction(conn):
        if file_row is not None:
            set_current_path(conn, int(row["file_id"]), str(from_path))
        reverse_undo(conn, int(row["id"]))
    if note_path and note_path.exists() and not read_user_edited(note_path):
        try:
            note_path.unlink(missing_ok=True)
        except Exception as exc:
            logging.warning("Failed to delete note during undo: %s", exc)
    return {"status": "ok", "message": f"Restored {from_path.name}."}
