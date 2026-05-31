from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from golem.constants import APP_NAME, APP_VERSION


def build_manifest(payload_dir: Path) -> dict[str, object]:
    files: list[dict[str, str]] = []
    for path in sorted(payload_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "payload-manifest.json":
            continue
        rel_path = path.relative_to(payload_dir).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"path": rel_path, "sha256": digest})
    return {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a payload manifest for a GOLEM bundle")
    parser.add_argument("payload_dir", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    payload_dir = args.payload_dir.resolve()
    if not payload_dir.exists() or not payload_dir.is_dir():
        raise FileNotFoundError(f"Payload directory not found: {payload_dir}")

    manifest = build_manifest(payload_dir)
    out_path = args.out or (payload_dir / "payload-manifest.json")
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
