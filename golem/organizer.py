from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .indexer import add_undo_log
from .utils import ensure_unique_path, safe_move


def organize_file(source_path: Path, vault_folder: Path, category: str, dry_run: bool = False) -> Path:
    target_root = vault_folder / "GOLEM Files" / category
    target_root.mkdir(parents=True, exist_ok=True)
    target_path = ensure_unique_path(target_root / source_path.name)
    if dry_run:
        return target_path
    safe_move(source_path, target_path)
    return target_path


def record_move(conn, file_id: int, from_path: str, to_path: str) -> int:
    timestamp = datetime.now(UTC).isoformat()
    return add_undo_log(conn, "move", file_id, from_path, to_path, timestamp)

