from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Iterable


def sha256_file(path: Path, max_bytes: int | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        remaining = max_bytes
        while True:
            chunk_size = 8192 if remaining is None else min(8192, remaining)
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
                if remaining <= 0:
                    break
    return digest.hexdigest()


def humanize_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    if not stem:
        stem = "Untitled"
    return stem[:1].upper() + stem[1:]


def slugify_name(name: str) -> str:
    clean = re.sub(r"[^\w\s\-().]+", "", name, flags=re.UNICODE)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or "Untitled"


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def is_hidden_or_system_dir(name: str) -> bool:
    return name.startswith(".") or name.startswith("$") or name in {
        "System Volume Information",
        "$Recycle.Bin",
        "$RECYCLE.BIN",
    }


def normalize_tags(tags: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        tag = re.sub(r"\s+", " ", tag).strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        result.append(tag)
    return result[:8]


def text_excerpt(text: str, limit: int = 300) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", text)]


def within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False

