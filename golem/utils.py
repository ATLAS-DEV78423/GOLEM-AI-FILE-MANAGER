from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Iterable
from pathlib import Path


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
    """Return a path that does not yet exist on disk.

    The path is returned unchanged if it does not exist. Otherwise, an integer
    suffix is appended before the file extension: ``"report.txt"`` becomes
    ``"report (1).txt"`` and so on until a free name is found.

    The previous implementation called ``path.touch()`` then ``path.unlink()``
    to test existence. That left a TOCTOU window and could leave 0-byte
    artefacts on SMB shares with antivirus scanners. The check is now a
    straight ``exists()`` call, which is correct for our use case (we want a
    *free* name, not to atomically claim one).
    """
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
        if counter > 10_000:
            # Defensive: pathological case where the directory is being
            # flooded with same-named files. Bail rather than spin forever.
            raise RuntimeError(f"Could not find a unique name for {path} after 10000 attempts")


def is_hidden_or_system_dir(name: str) -> bool:
    return (
        name.startswith(".")
        or name.startswith("$")
        or name
        in {
            "System Volume Information",
            "$Recycle.Bin",
            "$RECYCLE.BIN",
        }
    )


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


def safe_move(src: Path, dst: Path) -> None:
    """Move src to dst reliably across platforms.

    On Windows, shutil.move raises when crossing volume boundaries
    (e.g. watched folder on C: and vault on D:). On macOS, it can fail when
    the source is on an SMB share with strict ACLs. We try the fast path
    (shutil.move, which is just a rename on the same volume) and fall
    back to a copy + unlink on ANY failure. The fallback is slower on
    same-volume moves but always correct.

    The destination's parent is created if missing. The destination will
    not exist before this call unless it was created concurrently; that
    case is left to the caller (use ensure_unique_path upstream).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(src), str(dst))
        return
    except (OSError, shutil.Error):
        # Any failure — cross-volume, locked file, ACL, network share
        # glitch, missing permission — fall through to a copy + unlink.
        # This is slower but always works for files we can read and write.
        pass
    shutil.copy2(str(src), str(dst))
    try:
        src.unlink()
    except OSError as exc:
        # The copy succeeded but we couldn't remove the source. The user
        # now has a duplicate. Surface a clear error so the caller can
        # log and decide how to recover.
        raise OSError(f"Copied {src} to {dst} but failed to delete the source: {exc}") from exc
