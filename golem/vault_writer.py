from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .indexer import FileRecord
from .utils import ensure_unique_path


def _clean_text(value: str) -> str:
    return " ".join(str(value).split())


def _frontmatter(record: FileRecord) -> str:
    tags = [tag.strip() for tag in record.tags.split(",") if tag.strip()]
    tags_repr = json.dumps(tags, ensure_ascii=False)
    user_edited_flag = "true" if int(record.user_edited or 0) else "false"
    return "\n".join(
        [
            "---",
            f"filename: {json.dumps(_clean_text(record.clean_filename), ensure_ascii=False)}",
            f"original_name: {json.dumps(_clean_text(record.original_filename), ensure_ascii=False)}",
            f"path: {json.dumps(_clean_text(record.current_path), ensure_ascii=False)}",
            f"type: {json.dumps(_clean_text(record.file_type), ensure_ascii=False)}",
            f"size: {record.size_kb:.2f}KB",
            f"date_indexed: {json.dumps(_clean_text(record.date_indexed), ensure_ascii=False)}",
            f"tags: {tags_repr}",
            f"golem_category: {json.dumps(_clean_text(record.category), ensure_ascii=False)}",
            f"user_edited: {user_edited_flag}",
            "---",
        ]
    )


def _body(record: FileRecord) -> str:
    title = Path(_clean_text(record.clean_filename)).stem
    return "\n".join(
        [
            "",
            f"# {title}",
            "",
            f"**Summary:** {_clean_text(record.summary)}",
            "",
            f"**Key contents:** {_clean_text(record.key_contents)}",
            "",
            f"**Moved to:** `GOLEM Files/{_clean_text(record.category)}/`",
            "",
            f"[[{_clean_text(record.category)}]]",
            "",
        ]
    )


def note_path_for(vault_folder: Path, clean_filename: str) -> Path:
    """Return the path where an Obsidian note for ``clean_filename`` should live.

    Pure path computation. The caller is responsible for creating the parent
    directory before writing (see ``write_note``).
    """
    golem_dir = vault_folder / "GOLEM"
    return ensure_unique_path(golem_dir / f"{Path(clean_filename).stem}.md")


def read_user_edited(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        content = path.read_text(encoding="utf-8")
        return "user_edited: true" in content.lower()
    except Exception:
        return False


def write_note(vault_folder: Path, record: FileRecord) -> Path:
    note_path = note_path_for(vault_folder, record.clean_filename)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join([_frontmatter(record), _body(record)])
    note_path.write_text(content, encoding="utf-8")
    return note_path


def archive_orphan_note(vault_folder: Path, note_path: str) -> Path | None:
    path = Path(note_path)
    if not path.exists():
        return None
    if read_user_edited(path):
        return None
    orphan_dir = vault_folder / "GOLEM" / "Orphaned"
    orphan_dir.mkdir(parents=True, exist_ok=True)
    target = ensure_unique_path(orphan_dir / path.name)
    path.replace(target)
    return target
